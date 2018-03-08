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
 - convert integer fields to integers, including `len` of `set_xattr`,
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


class DumpItem(type):
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
    def parse_details(cls, details: bytes) -> Optional[Dict[str, Any]]:
        m = cls.regex.fullmatch(details)
        return {
            # Handle conv_FIELD_NAME class methods for converting fields.
            k: getattr(cls, f'conv_{k}', lambda x: x)(v)
                for k, v in m.groupdict().items()
        } if m else None


class DumpItems:
    '''
    This class only exists to group its inner classes, see NAME_TO_ITEM_TYPE.

    This list should exactly match the content of `btrfs_print_send_ops` in
    https://github.com/kdave/btrfs-progs/blob/master/send-dump.c

    Exceptions:
     - `from` in `clone` became `from_file` due to `namedtuple` limitations.
    '''

    class subvol(RegexParsedItem, metaclass=DumpItem):
        fields = ['uuid', 'transid']
        regex = re.compile(
            br'uuid=(?P<uuid>[-0-9a-f]+) '
            br'transid=(?P<transid>[0-9]+)'
        )

    class snapshot(RegexParsedItem, metaclass=DumpItem):
        fields = ['uuid', 'transid', 'parent_uuid', 'parent_transid']
        regex = re.compile(
            br'uuid=(?P<uuid>[-0-9a-f]+) '
            br'transid=(?P<transid>[0-9]+) '
            br'parent_uuid=(?P<parent_uuid>[-0-9a-f]+) '
            br'parent_transid=(?P<parent_transid>[0-9]+)'
        )

    class mkfile(RegexParsedItem, metaclass=DumpItem):
        pass

    class mkdir(RegexParsedItem, metaclass=DumpItem):
        pass

    class mknod(RegexParsedItem, metaclass=DumpItem):
        fields = ['mode', 'dev']  # octal & hex
        regex = re.compile(br'mode=(?P<mode>[0-7]+) dev=0x(?P<dev>[0-9a-f]+)')

    class mkfifo(RegexParsedItem, metaclass=DumpItem):
        pass

    class mksock(RegexParsedItem, metaclass=DumpItem):
        pass

    class symlink(RegexParsedItem, metaclass=DumpItem):
        fields = ['dest']  # This path is not quoted in `send-dump.c`
        regex = re.compile(br'dest=(?P<dest>.*)')

    class rename(RegexParsedItem, metaclass=DumpItem):
        fields = ['dest']  # This path is not quoted in `send-dump.c`
        regex = re.compile(br'dest=(?P<dest>.*)')

        @classmethod
        def conv_dest(cls, p: bytes) -> bytes:
            'normalize this the same way we normalize "path".'
            return os.path.normpath(p)

    class link(RegexParsedItem, metaclass=DumpItem):
        fields = ['dest']  # This path is not quoted in `send-dump.c`
        regex = re.compile(br'dest=(?P<dest>.*)')

    class unlink(RegexParsedItem, metaclass=DumpItem):
        pass

    class rmdir(RegexParsedItem, metaclass=DumpItem):
        pass

    class write(RegexParsedItem, metaclass=DumpItem):
        # NB: `btrfs receive --dump` omits the `data` field here (because it
        # would, naturally, be quite large.  For this reason, we still have
        # to compare the filesystem data separately from this tool.
        fields = ['offset', 'len']
        regex = re.compile(br'offset=(?P<offset>[0-9]+) len=(?P<len>[0-9]+)')

    class clone(RegexParsedItem, metaclass=DumpItem):
        # The path `from` is not quoted in `send-dump.c`, but a greedy
        # regex can still parse this fixed format correctly.
        #
        # We have to name it `from_file` due to `namedtuple` constraints.
        fields = ['offset', 'len', 'from_file', 'clone_offset']
        regex = re.compile(
            br'offset=(?P<offset>[0-9]+) '
            br'len=(?P<len>[0-9]+) '
            br'from=(?P<from_file>.+) '
            br'clone_offset=(?P<clone_offset>[0-9]+)'
        )

        @classmethod
        def conv_from_file(cls, p: bytes) -> bytes:
            'normalize this the same way we normalize "path".'
            return os.path.normpath(p)

    class set_xattr(metaclass=DumpItem):
        # IMPORTANT: `len` will generally be greater than `len(data)`
        # because at present, `btrfs` prints xattrs with this `printf`:
        #   "name=%s data=%.*s len=%d", name, len, (char *)data, len
        # The end result is that `data` gets printed up to the first \0.
        fields = ['name', 'data', 'len']

        # This cannot be parsed unambiguously with a single regex because
        # both `name` and `data` can contain arbitrary bytes, and neither is
        # quoted.
        first_regex = re.compile(br'(.*) len=([0-9]+)')
        second_regex = re.compile(br'name=(.*) data=')

        @classmethod
        def parse_details(cls, details: bytes) -> Optional[Dict[str, Any]]:
            m = cls.first_regex.fullmatch(details)
            if not m:
                return None
            rest = m.group(1)

            # An awful hack to deal with the fact that we cannot
            # unambiguously parse this name / data line as implemented.
            # First, we trust that all of `data` was printed.  If that
            # doesn't work, we try again, assuming that it just has a
            # trailing \0 byte. If that doesn't work either, we give up.
            length = m.group(2)
            for i in range(2):
                end_of_data = len(rest) - int(length) + i
                m = cls.second_regex.fullmatch(rest[:end_of_data])
                if m:
                    return {
                        'name': m.group(1),
                        'data': rest[end_of_data:],
                        'len': length,
                    }
            return None

    class remove_xattr(RegexParsedItem, metaclass=DumpItem):
        fields = ['name']  # This name is not quoted in `send-dump.c`
        regex = re.compile(br'name=(?P<name>.*)')

    class truncate(RegexParsedItem, metaclass=DumpItem):
        fields = ['size']
        regex = re.compile(br'size=(?P<size>[0-9]+)')

    class chmod(RegexParsedItem, metaclass=DumpItem):
        fields = ['mode']
        regex = re.compile(br'mode=(?P<mode>[0-7]+)')  # octal

    class chown(RegexParsedItem, metaclass=DumpItem):
        fields = ['gid', 'uid']
        regex = re.compile(br'gid=(?P<gid>[0-9]+) uid=(?P<uid>[0-9]+)')

    class utimes(RegexParsedItem, metaclass=DumpItem):
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


# The inner classes of DumpItems, after filtering out things like __doc__.
# The keys must be bytes because `btrfs` does not give us unicode.
NAME_TO_ITEM_TYPE = {
    k.encode(): v for k, v in DumpItems.__dict__.items() if k[0] != '_'
}


def parse_btrfs_dump(binary_infile: BinaryIO) -> Iterable[DumpItem]:
    reg = re.compile(br'([^ ]+) +((\\ |[^ ])+) *(.*)\n')
    for l in binary_infile:
        m = reg.fullmatch(l)
        if not m:
            raise RuntimeError(f'line has unexpected format: {repr(l)}')
        item_name, path, _, details = m.groups()

        item_class = NAME_TO_ITEM_TYPE.get(item_name)
        if not item_class:
            raise RuntimeError(f'unknown item type {item_name} in {repr(l)}')

        fields = item_class.parse_details(details)
        if fields is None:
            raise RuntimeError(f'unexpected format in line details: {repr(l)}')

        assert 'path' not in fields, f'{item_name}.regex defined <path>'
        # We MUST unquote here, or paths in field 1 will not be comparable
        # with as-of-now unquoted paths in the other fields.  For example,
        # `ItemFilters.rename` compares such paths.
        #
        # `normpath` is useful since `btrfs receive --dump` is inconsistent
        # about trailing slashes on directory paths.
        fields['path'] = os.path.normpath(unquote_btrfs_progs_path(path))

        yield item_class(**fields)


def get_frequency_of_selinux_xattrs(items):
    'Returns {"xattr_value": <count>}. Useful for ItemFilters.selinux_xattr.'
    counter = Counter()
    for item in items:
        if isinstance(item, DumpItems.set_xattr):
            if item.name == _SELINUX_XATTR:
                counter[item.data] += 1
    return counter


class ItemFilters:
    '''
    A namespace of filters for taking a just-parsed Iterable[DumpItems], and
    making it useful for filesystem testing.
    '''

    @staticmethod
    def selinux_xattr(
        items: Iterable[DumpItem],
        discard_fn: Callable[[bytes, bytes], bool],
    ) -> Iterable[DumpItem]:
        '''
        SELinux always sets a security context on filesystem objects, but most
        images will not ship data with non-default contexts, so it is easiest to
        just filter out these `set_xattr`s
        '''
        for item in items:
            if isinstance(item, DumpItems.set_xattr):
                if (
                    item.name == _SELINUX_XATTR and
                    discard_fn(item.path, item.data)
                ):
                    continue
            yield item

    @staticmethod
    def normalize_utimes(
        items: Iterable[DumpItem],
        start_time: float,
        end_time: float,
    ) -> Iterable[DumpItem]:
        '''
        Build-time timestamps will vary, since the build takes some time.
        We can make them predictable by replacing any timestamp within the
        build time-range by `start_time`.
        '''
        def normalize_time(t):
            return start_time if start_time <= t <= end_time else t

        for item in items:
            if isinstance(item, DumpItems.utimes):
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
