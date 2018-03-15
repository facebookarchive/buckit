#!/usr/bin/env python3
import io
import logging
import os
import subprocess
import unittest

from artifacts_dir import get_per_repo_artifacts_dir
from volume_for_repo import get_volume_for_current_repo

from ..parse_dump import (
    SendStreamItems, NAME_TO_PARSER_TYPE, parse_btrfs_dump,
    unquote_btrfs_progs_path,
)
from ..send_stream import get_frequency_of_selinux_xattrs, ItemFilters
from ..subvol_path import SubvolPath

# `unittest`'s output shortening makes tests much harder to debug.
unittest.util._MAX_LENGTH = 10e4


def _sibling_path(rel_path):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)


def _parse_bytes_to_list(s):
    return list(parse_btrfs_dump(io.BytesIO(s)))


class ParseBtrfsDumpTestCase(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 10e4

    def test_unquote(self):
        self.assertEqual(
            (b'\a\b\x1b\f\n\r\t\v ' br'\XYZ\F\0\O\P'),
            unquote_btrfs_progs_path(
                # Special escapes
                br'\a\b\e\f\n\r\t\v\ \\' +
                # Octal escapes
                ''.join(f'\\{ord(c):o}' for c in 'XYZ').encode('ascii') +
                # Unrecognized escapes will be left alone
                br'\F\0\O\P'
            )
        )

    def test_ensure_print_demo_dump_covers_all_operations(self):
        print_demo_dump_sh = _sibling_path('print_demo_dump.sh')
        out_bytes = subprocess.check_output(
            ['sudo', print_demo_dump_sh],
            cwd=get_volume_for_current_repo(1e8, get_per_repo_artifacts_dir()),
        )
        out_lines = out_bytes.rstrip(b'\n').split(b'\n')
        # Ensure we have exercised all the implemented operations:
        # https://github.com/kdave/btrfs-progs/blob/master/send-dump.c#L319
        expected_ops = {
            'chmod',
            'chown',
            'clone',
            'link',
            'mkdir',
            'mkfifo',
            'mkfile',
            'mknod',
            'mksock',
            'remove_xattr',
            'rename',
            'rmdir',
            'set_xattr',
            'snapshot',
            'subvol',
            'symlink',
            'truncate',
            'unlink',
            'update_extent',
            'utimes',
            # Omitted since `--dump` never prints data: 'write',
        }
        self.assertEqual(
            {n.decode() for n in NAME_TO_PARSER_TYPE.keys()},
            expected_ops,
        )
        self.assertEqual(
            expected_ops,
            {l.split(b' ', 1)[0].decode() for l in out_lines if l} - {'write'},
        )
        items = _parse_bytes_to_list(out_bytes)
        # We an item per line, and the items cover the expected operations.
        self.assertEqual(len(items), len(out_lines))
        self.assertEqual(
            {getattr(SendStreamItems, op_name) for op_name in expected_ops},
            {i.__class__ for i in items},
        )

    # The reason we want to parse a gold file instead of, as above, running
    # `print_demo_dump.sh` is explained in `update_gold_print_demo_dump.sh`.
    def test_verify_gold_parse(self):
        with open(_sibling_path('gold_print_demo_dump.out'), 'rb') as infile:
            lines = infile.readlines()
        build_start_time, build_end_time = (
            float(l) for l in [lines[0], lines[-1]]
        )
        orig_items = _parse_bytes_to_list(b''.join(lines[1:-1]))
        items = orig_items

        # Our test program does not touch the SELinux context, so if it's
        # set, it will be set to the default, and we can just filter out the
        # most frequent value.  We don't want to drop selinux attributes
        # blindly because having varying contexts suggests something broken
        # about the test or our environment.
        selinux_freqs = get_frequency_of_selinux_xattrs(orig_items)
        self.assertGreater(len(selinux_freqs), 0)  # `gold` has SELinux attrs
        max_name, _count = max(selinux_freqs.items(), key=lambda p: p[1])
        logging.info(f'This test ignores SELinux xattrs set to {max_name}')
        items = ItemFilters.selinux_xattr(
            items,
            discard_fn=lambda _path, ctx: ctx == max_name,
        )
        items = ItemFilters.normalize_utimes(
            items, start_time=build_start_time, end_time=build_end_time,
        )
        items = list(items)

        di = SendStreamItems

        def p(path):
            if isinstance(path, str):  # forgive missing `b`s, it's a test
                path = path.encode()
            return SubvolPath._new(path)

        def chown(path):
            return di.chown(path=p(path), gid=0, uid=0)

        def chmod(path, mode=0o644):
            return di.chmod(path=p(path), mode=mode)

        def utimes(path):
            return di.utimes(
                path=p(path),
                atime=build_start_time,
                mtime=build_start_time,
                ctime=build_start_time,
            )

        def base_metadata(path, mode=0o644):
            return [chown(path), chmod(path, mode), utimes(path)]

        # Future: if we end up doing a lot of mid-list insertions, we can
        # autogenerate the temporary names to match what btrfs does.
        def and_rename(item, real_name, utimes_parent=True):
            yield item
            renamed_item = di.rename(
                path=item.path,
                dest=p(
                    os.path.join(os.path.dirname(bytes(item.path)), real_name)
                ),
            )
            yield renamed_item
            if utimes_parent:  # Rarely, `btrfs send` breaks the pattern.
                yield utimes(os.path.dirname(bytes(renamed_item.dest)))

        # These make it quite easy to update the test after you run
        # `update_gold_print_demo_dump.sh`.
        uuid_create = b'c065a6aa-c53c-624e-8f10-a2b080b9e580'
        transid_create = 2797
        uuid_mutate = b'32f71a40-1253-da49-81fe-0c182ed6cb79'
        transid_mutate = 2800
        temp_path_middles = {'create_ops': 2795, 'mutate_ops': 2799}
        temp_path_counter = 256  # I have never seen this initial value change.

        def temp_path(prefix):
            nonlocal temp_path_counter
            temp_path_counter += 1
            mid = temp_path_middles[prefix]
            return p(f'{prefix}/o{temp_path_counter}-{mid}-0')

        self.assertEqual([
            di.subvol(
                path=p('create_ops'), uuid=uuid_create, transid=transid_create,
            ),
            *base_metadata('create_ops', mode=0o755),

            *and_rename(di.mkdir(path=temp_path('create_ops')), b'hello'),
            di.set_xattr(
                path=p('create_ops/hello'),
                name=b'user.test_attr',
                data=b'chickens',
            ),
            *base_metadata('create_ops/hello', mode=0o755),

            *and_rename(
                di.mkdir(path=temp_path('create_ops')), b'dir_to_remove'
            ),
            *base_metadata('create_ops/dir_to_remove', mode=0o755),

            *and_rename(
                di.mkfile(path=temp_path('create_ops')), b'goodbye',
                utimes_parent=False,
            ),
            di.link(
                path=p('create_ops/hello/world'), dest=p('create_ops/goodbye'),
            ),
            utimes('create_ops'),
            utimes('create_ops/hello'),
            di.truncate(path=p('create_ops/goodbye'), size=0),
            *base_metadata('create_ops/goodbye'),

            *and_rename(di.mknod(
                path=temp_path('create_ops'), mode=0o60600, dev=0x7a539b7,
            ), b'buffered'),
            *base_metadata('create_ops/buffered', mode=0o600),

            *and_rename(di.mknod(
                path=temp_path('create_ops'), mode=0o20644, dev=0x7a539b7,
            ), b'unbuffered'),
            *base_metadata('create_ops/unbuffered'),

            *and_rename(di.mkfifo(path=temp_path('create_ops')), b'fifo'),
            *base_metadata('create_ops/fifo'),

            *and_rename(
                di.mksock(path=temp_path('create_ops')), b'unix_sock',
            ),
            *base_metadata('create_ops/unix_sock', mode=0o755),

            *and_rename(di.symlink(
                path=temp_path('create_ops'), dest=b'hello/world',
            ), b'goodbye_symbolic'),
            chown('create_ops/goodbye_symbolic'),
            utimes('create_ops/goodbye_symbolic'),

            *and_rename(
                di.mkfile(path=temp_path('create_ops')), b'1MB_nuls',
            ),
            di.update_extent(
                path=p('create_ops/1MB_nuls'), offset=0, len=2**20,
            ),
            di.truncate(path=p('create_ops/1MB_nuls'), size=2**20),
            *base_metadata('create_ops/1MB_nuls'),

            *and_rename(
                di.mkfile(path=temp_path('create_ops')), b'1MB_nuls_clone',
            ),
            di.clone(
                path=p('create_ops/1MB_nuls_clone'), offset=0, len=2**20,
                from_uuid=b'', from_transid=b'',
                from_path=p('create_ops/1MB_nuls'), clone_offset=0,
            ),
            di.truncate(path=p('create_ops/1MB_nuls_clone'), size=2**20),
            *base_metadata('create_ops/1MB_nuls_clone'),

            *and_rename(
                di.mkfile(path=temp_path('create_ops')), b'zeros_hole_zeros',
            ),
            di.update_extent(
                path=p('create_ops/zeros_hole_zeros'), offset=0, len=16384,
            ),
            di.update_extent(
                path=p('create_ops/zeros_hole_zeros'), offset=32768, len=16384,
            ),
            di.truncate(path=p('create_ops/zeros_hole_zeros'), size=49152),
            *base_metadata('create_ops/zeros_hole_zeros'),

            di.snapshot(
                path=p('mutate_ops'),
                uuid=uuid_mutate,
                transid=transid_mutate,
                parent_uuid=uuid_create,
                parent_transid=transid_create,
            ),
            utimes('mutate_ops'),
            di.rename(
                path=p('mutate_ops/hello'), dest=p('mutate_ops/hello_renamed'),
            ),
            utimes('mutate_ops'),
            utimes('mutate_ops'),  # `btrfs send` is not so parsimonious

            di.remove_xattr(
                path=p('mutate_ops/hello_renamed'), name=b'user.test_attr',
            ),
            utimes('mutate_ops/hello_renamed'),

            di.rmdir(path=p('mutate_ops/dir_to_remove')),
            utimes('mutate_ops'),

            di.link(
                path=p('mutate_ops/farewell'), dest=p('mutate_ops/goodbye'),
            ),
            di.unlink(path=p('mutate_ops/goodbye')),
            di.unlink(path=p('mutate_ops/hello_renamed/world')),
            utimes('mutate_ops'),
            utimes('mutate_ops'),
            utimes('mutate_ops/hello_renamed'),
            di.truncate(path=p('mutate_ops/farewell'), size=0),
            utimes('mutate_ops/farewell'),

            *and_rename(
                di.mkfile(path=temp_path('mutate_ops')), b'hello_renamed/een',
            ),
            di.update_extent(
                path=p('mutate_ops/hello_renamed/een'), offset=0, len=5,
            ),
            di.truncate(path=p('mutate_ops/hello_renamed/een'), size=5),
            *base_metadata('mutate_ops/hello_renamed/een'),
        ], items)

    def test_common_errors(self):
        ok_line = b'mkfile ./cat\\ and\\ dog\n'  # Drive-by test of unquoting
        self.assertEqual(
            [SendStreamItems.mkfile(path=SubvolPath._new(b'cat and dog'))],
            _parse_bytes_to_list(ok_line),
        )

        with self.assertRaisesRegex(RuntimeError, 'has unexpected format:'):
            _parse_bytes_to_list(b' ' + ok_line)

        with self.assertRaisesRegex(RuntimeError, "unknown item type b'Xmkfi"):
            _parse_bytes_to_list(b'X' + ok_line)

    def test_set_xattr_errors(self):

        def make_line(len_k='len', len_v=7, name_k='name', data_k='data'):
            return (
                'set_xattr       ./subvol/file                   '
                f'{name_k}=MY_ATTR {data_k}=MY_DATA {len_k}={len_v}\n'
            ).encode('ascii')

        # Before breaking it, ensure that `make_line` actually works
        for data in (b'MY_DATA', b'MY_DATA\0'):
            self.assertEqual(
                [SendStreamItems.set_xattr(
                    path=SubvolPath._new(b'subvol/file'),
                    name=b'MY_ATTR',
                    data=data,
                )],
                # The `--dump` line does NOT show the \0, the parser infers it.
                _parse_bytes_to_list(make_line(len_v=len(data))),
            )

        for bad_line in [
            # Bad field name, non-int value, value inconsistent with data,
            make_line(len_k='Xlen'), make_line(len_v='x7'), make_line(len_v=9),
            # Swap name & data fields, try a bad one
            make_line(data_k='name', name_k='data'), make_line(name_k='nom'),
        ]:
            with self.assertRaisesRegex(RuntimeError, 'in line details:'):
                _parse_bytes_to_list(bad_line)


if __name__ == '__main__':
    unittest.main()
