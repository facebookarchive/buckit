#!/usr/bin/env python3
'''
Library + demonstration tool for parsing the metadata contained in a `btrfs
send` stream, as printed by `btrfs receive --dump`.

Usage:

  btrfs send --no-data SUBVOL/ | btrfs receive --dump | parse_dump.py

The `--no-data` flag is optional, but should speed up the send & receive
considerably.  The parsed output will be similar because this code treats
`write` and `update_extent` items identically.  The only difference comes
from the fact that `send` emits sequential `write` instructions for
sequential chunks of an extent, but `update_extent` is emitted just once per
extent.

Limitations of `btrfs receive --dump` (filed as T25376790):
 - With the exception of the path of the object being manipulated by the
   current dump item, none of the string attributes (paths, xattr names &
   values) are quoted in the current version of `btrfs`. This means that
   if any of those values have a newline, we will fail to parse.
 - xattr values are only printed up to the first \\0 character, see `set_xattr`
 - timestamps are printed only to 1-second resolution, while

TODOs:
 - consider parsing the `btrfs send` stream directly, which should be both
   faster and more future-proof than relying on `--dump` output. Examples:
   https://github.com/osandov/osandov-linux/blob/master/scripts/btrfs-send-sanitize.py
'''
import datetime
import os
import re

from collections import Counter, OrderedDict
from compiler.enriched_namedtuple import metaclass_new_enriched_namedtuple
from typing import Any, BinaryIO, Callable, Dict, Iterable, Optional, Pattern

from .subvol_path import SubvolPath


_ESCAPED_TO_UNESCAPED = OrderedDict([
    (br'\a', b'\a'),
    (br'\b', b'\b'),
    (br'\e', b'\x1b'),
    (br'\f', b'\f'),
    (br'\n', b'\n'),
    (br'\r', b'\r'),
    (br'\t', b'\t'),
    (br'\v', b'\v'),
    (br'\ ', b' '),
    (b'\\\\', b'\\'),
    *[(f'\\{i:03o}'.encode('ascii'), bytes([i])) for i in range(256)],
    # For now: leave alone any backslashes not involved in a known path
    # escape sequence.  However, we could add fallbacks here.
])
# You can visualize the resulting table with this snippet:
#   print('\n'.join(
#       '\t'.join(
#           (
#               f'{e.decode("ascii")} -> {repr(u).lstrip("b")}'
#                   if (e, u) != (None, None) else ''
#           ) for e, u in group
#       ) for group in itertools.zip_longest(
#           *([iter(_ESCAPED_TO_UNESCAPED.items())] * 5),
#           fillvalue=(None, None),
#       )
#   ))
_ESCAPED_REGEX = re.compile(
    b'|'.join(re.escape(e) for e in _ESCAPED_TO_UNESCAPED)
)
_SELINUX_XATTR = b'security.selinux'


def unquote_btrfs_progs_path(s):
    '''
    `btrfs receive --dump` always quotes the first field of an item -- the
    subvolume path being touched.  Its quoting is similar to C, but
    idiosyncratic (see `print_path_escaped` in `send-dump.c`), so we need a
    custom un-quoting function.  Future: fix `btrfs-progs` so that other
    fields (paths & data) are quoted too.
    '''
    return _ESCAPED_REGEX.sub(lambda m: _ESCAPED_TO_UNESCAPED[m.group(0)], s)


class SendStreamItem(type):
    'Metaclass for the types of lines that `btrfs receive --dump` produces.'
    def __new__(metacls, classname, bases, dct):
        return metaclass_new_enriched_namedtuple(
            __class__,
            ['path'],
            metacls, classname, bases, dct
        )


class RegexParsedItem:
    'Almost all item types can be parsed with a single regex.'
    __slots__ = ()

    regex: Pattern = re.compile(b'')

    @classmethod
    def parse_details(
        cls, path: SubvolPath, details: bytes
    ) -> Optional[Dict[str, Any]]:
        m = cls.regex.fullmatch(details)
        return {
            # Handle `conv_FIELD_NAME` class methods for converting fields.
            # These take a single positional argument, and handle most
            # cases.
            #
            # We currently only use `context_conv_FIELD_NAME` when a detail
            # field needs to know the path to process correctly, see `link`.
            k: getattr(
                cls, f'context_conv_{k}', lambda value, path: value
            )(
                getattr(cls, f'conv_{k}', lambda x: x)(v),
                path=path,
            )
                for k, v in m.groupdict().items()
        } if m else None


def _from_octal(s: bytes) -> int:
    return int(s, base=8)


class SendStreamItems:
    '''
    This class only exists to group its inner classes, see NAME_TO_ITEM_TYPE.

    This list should exactly match the content of `btrfs_print_send_ops` in
    https://github.com/kdave/btrfs-progs/blob/master/send-dump.c

    Exceptions:
     - `from` in `clone` became `from_path` due to `namedtuple` limitations.
    '''

    #
    # operations making new subvolumes
    #

    class subvol(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['uuid', 'transid']
        regex = re.compile(
            br'uuid=(?P<uuid>[-0-9a-f]+) '
            br'transid=(?P<transid>[0-9]+)'
        )
        conv_transid = staticmethod(int)

    class snapshot(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['uuid', 'transid', 'parent_uuid', 'parent_transid']
        regex = re.compile(
            br'uuid=(?P<uuid>[-0-9a-f]+) '
            br'transid=(?P<transid>[0-9]+) '
            br'parent_uuid=(?P<parent_uuid>[-0-9a-f]+) '
            br'parent_transid=(?P<parent_transid>[0-9]+)'
        )
        conv_transid = staticmethod(int)
        conv_parent_transid = staticmethod(int)

    #
    # operations making new inodes
    #

    class mkfile(RegexParsedItem, metaclass=SendStreamItem):
        pass

    class mkdir(RegexParsedItem, metaclass=SendStreamItem):
        pass

    class mknod(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['mode', 'dev']
        regex = re.compile(br'mode=(?P<mode>[0-7]+) dev=0x(?P<dev>[0-9a-f]+)')
        conv_mode = staticmethod(_from_octal)

        @staticmethod
        def conv_dev(dev: bytes) -> int:
            return int(dev, base=16)

    class mkfifo(RegexParsedItem, metaclass=SendStreamItem):
        pass

    class mksock(RegexParsedItem, metaclass=SendStreamItem):
        pass

    class symlink(RegexParsedItem, metaclass=SendStreamItem):
        # NB unlike the paths in other items, the symlink target is just an
        # arbitrary string with no filesystem signficance, so we do not
        # process it at all.  Unfortunately, `dest` is not quoted in
        # `send-dump.c`.
        fields = ['dest']
        regex = re.compile(br'dest=(?P<dest>.*)')

    #
    # operations on the path -> inode mapping
    #

    class rename(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['dest']  # This path is not quoted in `send-dump.c`
        regex = re.compile(br'dest=(?P<dest>.*)')
        conv_dest = staticmethod(SubvolPath._new)  # Normalize like .path

    class link(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['dest']  # This path is not quoted in `send-dump.c`
        regex = re.compile(br'dest=(?P<dest>.*)')

        # `btrfs receive` is inconsistent -- unlike other paths, its `dest`
        # does not start with the subvolume path.
        @staticmethod
        def context_conv_dest(dest: bytes, path: SubvolPath) -> SubvolPath:
            return SubvolPath(
                subvol=path.subvol,
                path=os.path.normpath(dest),
            )

    class unlink(RegexParsedItem, metaclass=SendStreamItem):
        pass

    class rmdir(RegexParsedItem, metaclass=SendStreamItem):
        pass

    #
    # per-inode operations
    #

    class write(RegexParsedItem, metaclass=SendStreamItem):
        # NB: `btrfs receive --dump` omits the `data` field here (because it
        # would, naturally, be quite large.  For this reason, we still have
        # to compare the filesystem data separately from this tool.
        fields = ['offset', 'len']
        regex = re.compile(br'offset=(?P<offset>[0-9]+) len=(?P<len>[0-9]+)')
        conv_offset = staticmethod(int)
        conv_len = staticmethod(int)

    class clone(RegexParsedItem, metaclass=SendStreamItem):
        # The path `from` is not quoted in `send-dump.c`, but a greedy
        # regex can still parse this fixed format correctly.
        #
        # We have to name it `from_path` since `from` is a reserved keyword.
        fields = ['offset', 'len', 'from_path', 'clone_offset']
        regex = re.compile(
            br'offset=(?P<offset>[0-9]+) '
            br'len=(?P<len>[0-9]+) '
            br'from=(?P<from_path>.+) '
            br'clone_offset=(?P<clone_offset>[0-9]+)'
        )
        conv_offset = staticmethod(int)
        conv_len = staticmethod(int)
        conv_from_path = staticmethod(SubvolPath._new)  # Normalize like .path
        conv_clone_offset = staticmethod(int)

    class set_xattr(metaclass=SendStreamItem):
        # The `len` field is just `len(data)`, but see the caveat below.
        fields = ['name', 'data']

        # This cannot be parsed unambiguously with a single regex because
        # both `name` and `data` can contain arbitrary bytes, and neither is
        # quoted.
        first_regex = re.compile(br'(.*) len=([0-9]+)')
        second_regex = re.compile(br'name=(.*) data=')

        @classmethod
        def parse_details(
            cls, path: SubvolPath, details: bytes,
        ) -> Optional[Dict[str, Any]]:
            m = cls.first_regex.fullmatch(details)
            if not m:
                return None
            rest = m.group(1)

            # An awful hack to deal with the fact that we cannot
            # unambiguously parse this name / data line as implemented.
            # The reason is that, `btrfs receive --dump` prints xattrs with
            # this `printf`:
            #   "name=%s data=%.*s len=%d", name, len, (char *)data, len
            # The end result is that `data` gets printed up to the first \0.
            #
            # Our workaround is to first assume that all of `data` was
            # printed.  If that doesn't work, we try again, assuming that it
            # just has a trailing \0 byte.  If that doesn't work either, we
            # give up.
            #
            # The alternative would be for the parse to store `len` &
            # `data`, with `len(data) < len` in some cases.  This seems
            # broken and useless, and makes downstream code harder.  If we
            # need to support xattrs with \0 chars in the middle, we should
            # either fix `btrfs receive --dump` to do quoting, or just parse
            # the binary send-stream.
            length = m.group(2)
            for has_trailing_nul in [False, True]:
                end_of_data = len(rest) - int(length) + has_trailing_nul
                m = cls.second_regex.fullmatch(rest[:end_of_data])
                data = rest[end_of_data:]
                if has_trailing_nul:
                    data += b'\0'
                assert len(data) == int(length)  # We don't need to store `len`
                if m:
                    return {'name': m.group(1), 'data': data}
            return None

    class remove_xattr(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['name']  # This name is not quoted in `send-dump.c`
        regex = re.compile(br'name=(?P<name>.*)')

    class truncate(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['size']
        regex = re.compile(br'size=(?P<size>[0-9]+)')
        conv_size = staticmethod(int)

    class chmod(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['mode']
        regex = re.compile(br'mode=(?P<mode>[0-7]+)')
        conv_mode = staticmethod(_from_octal)

    class chown(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['gid', 'uid']
        regex = re.compile(br'gid=(?P<gid>[0-9]+) uid=(?P<uid>[0-9]+)')
        conv_gid = staticmethod(int)
        conv_uid = staticmethod(int)

    class utimes(RegexParsedItem, metaclass=SendStreamItem):
        fields = ['atime', 'mtime', 'ctime']
        regex = re.compile(
            br'atime=(?P<atime>[^ ]+) '
            br'mtime=(?P<mtime>[^ ]+) '
            br'ctime=(?P<ctime>[^ ]+)'
        )

        @classmethod
        def conv_atime(cls, t: bytes) -> float:
            return datetime.datetime.strptime(
                t.decode(), '%Y-%m-%dT%H:%M:%S%z'
            ).timestamp()

        conv_mtime = conv_atime
        conv_ctime = conv_atime

    # This is literally the same thing as `write`, but emitted when `btrfs
    # send --no-data` is used.  Identify the two for test coverage's sake.
    update_extent = write


# The inner classes of SendStreamItems, after filtering out things like __doc__.
# The keys must be bytes because `btrfs` does not give us unicode.
NAME_TO_ITEM_TYPE = {
    k.encode(): v for k, v in SendStreamItems.__dict__.items() if k[0] != '_'
}


def parse_btrfs_dump(binary_infile: BinaryIO) -> Iterable[SendStreamItem]:
    reg = re.compile(br'([^ ]+) +((\\ |[^ ])+) *(.*)\n')
    for l in binary_infile:
        m = reg.fullmatch(l)
        if not m:
            raise RuntimeError(f'line has unexpected format: {repr(l)}')
        item_name, path, _, details = m.groups()

        item_class = NAME_TO_ITEM_TYPE.get(item_name)
        if not item_class:
            raise RuntimeError(f'unknown item type {item_name} in {repr(l)}')

        # We MUST unquote here, or paths in field 1 will not be comparable
        # with as-of-now unquoted paths in the other fields.  For example,
        # `ItemFilters.rename` compares such paths.
        path = SubvolPath._new(unquote_btrfs_progs_path(path))

        fields = item_class.parse_details(path, details)
        if fields is None:
            raise RuntimeError(f'unexpected format in line details: {repr(l)}')

        assert 'path' not in fields, f'{item_name}.regex defined <path>'
        fields['path'] = path

        yield item_class(**fields)


def get_frequency_of_selinux_xattrs(items):
    'Returns {"xattr_value": <count>}. Useful for ItemFilters.selinux_xattr.'
    counter = Counter()
    for item in items:
        if isinstance(item, SendStreamItems.set_xattr):
            if item.name == _SELINUX_XATTR:
                counter[item.data] += 1
    return counter


class ItemFilters:
    '''
    A namespace of filters for taking a just-parsed Iterable[SendStreamItems],
    and making it useful for filesystem testing.
    '''

    @staticmethod
    def selinux_xattr(
        items: Iterable[SendStreamItem],
        discard_fn: Callable[[bytes, bytes], bool],
    ) -> Iterable[SendStreamItem]:
        '''
        SELinux always sets a security context on filesystem objects, but most
        images will not ship data with non-default contexts, so it is easiest to
        just filter out these `set_xattr`s
        '''
        for item in items:
            if isinstance(item, SendStreamItems.set_xattr):
                if (
                    item.name == _SELINUX_XATTR and
                    discard_fn(item.path, item.data)
                ):
                    continue
            yield item

    @staticmethod
    def normalize_utimes(
        items: Iterable[SendStreamItem],
        start_time: float,
        end_time: float,
    ) -> Iterable[SendStreamItem]:
        '''
        Build-time timestamps will vary, since the build takes some time.
        We can make them predictable by replacing any timestamp within the
        build time-range by `start_time`.
        '''
        def normalize_time(t):
            return start_time if start_time <= t <= end_time else t

        for item in items:
            if isinstance(item, SendStreamItems.utimes):
                yield type(item)(
                    path=item.path,
                    atime=normalize_time(item.atime),
                    mtime=normalize_time(item.mtime),
                    ctime=normalize_time(item.ctime),
                )
            else:
                yield item


if __name__ == '__main__':  # pragma: no cover
    import sys
    for item in parse_btrfs_dump(sys.stdin.buffer):
        print(item)
