#!/usr/bin/env python3
import io
import os
import pickle
import subprocess
import unittest

from typing import List, Sequence

from ..parse_dump import (
    NAME_TO_PARSER_TYPE, parse_btrfs_dump, unquote_btrfs_progs_path,
)
from ..send_stream import (
    get_frequency_of_selinux_xattrs, ItemFilters, SendStreamItem,
    SendStreamItems,
)
from ..subvol_path import SubvolPath

from .demo_sendstreams import sudo_demo_sendstreams, sibling_path
from .demo_sendstreams_expected import get_filtered_and_expected_items

# `unittest`'s output shortening makes tests much harder to debug.
unittest.util._MAX_LENGTH = 10e4


def _parse_lines_to_list(s: Sequence[bytes]) -> List[SendStreamItem]:
    return list(parse_btrfs_dump(io.BytesIO(b'\n'.join(s) + b'\n')))


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

    def test_ensure_demo_sendstreams_cover_all_operations(self):
        # Ensure we have implemented all the operations from here:
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

        # Now check that `demo_sendstream.py` also exercises those operations.
        stream_dict = sudo_demo_sendstreams()
        out_lines = [
            *stream_dict['create_ops']['dump'],
            *stream_dict['mutate_ops']['dump'],
        ]
        self.assertEqual(
            expected_ops,
            {l.split(b' ', 1)[0].decode() for l in out_lines if l} - {'write'},
        )
        items = _parse_lines_to_list(out_lines)
        # We an item per line, and the items cover the expected operations.
        self.assertEqual(len(items), len(out_lines))
        self.assertEqual(
            {getattr(SendStreamItems, op_name) for op_name in expected_ops},
            {i.__class__ for i in items},
        )

    # The reason we want to parse a gold file instead of, as above, running
    # `demo_sendstreams.py` is explained in its top docblock.
    def test_verify_gold_parse(self):
        with open(sibling_path('gold_demo_sendstreams.pickle'), 'rb') as f:
            stream_dict = pickle.load(f)

        filtered_items, expected_items = get_filtered_and_expected_items(
            items=_parse_lines_to_list([
                *stream_dict['create_ops']['dump'],
                *stream_dict['mutate_ops']['dump'],
            ]),
            # `--dump` does not show fractional seconds at present.
            build_start_time=int(
                stream_dict['create_ops']['build_start_time']
            ),
            build_end_time=int(stream_dict['mutate_ops']['build_end_time']),
        )
        self.assertEqual(filtered_items, expected_items)

    def test_common_errors(self):
        ok_line = b'mkfile ./cat\\ and\\ dog'  # Drive-by test of unquoting
        self.assertEqual(
            [SendStreamItems.mkfile(path=SubvolPath._new(b'cat and dog'))],
            _parse_lines_to_list([ok_line]),
        )

        with self.assertRaisesRegex(RuntimeError, 'has unexpected format:'):
            _parse_lines_to_list([b' ' + ok_line])

        with self.assertRaisesRegex(RuntimeError, "unknown item type b'Xmkfi"):
            _parse_lines_to_list([b'X' + ok_line])

    def test_set_xattr_errors(self):

        def make_line(len_k='len', len_v=7, name_k='name', data_k='data'):
            return (
                'set_xattr       ./subvol/file                   '
                f'{name_k}=MY_ATTR {data_k}=MY_DATA {len_k}={len_v}'
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
                _parse_lines_to_list([make_line(len_v=len(data))]),
            )

        for bad_line in [
            # Bad field name, non-int value, value inconsistent with data,
            make_line(len_k='Xlen'), make_line(len_v='x7'), make_line(len_v=9),
            # Swap name & data fields, try a bad one
            make_line(data_k='name', name_k='data'), make_line(name_k='nom'),
        ]:
            with self.assertRaisesRegex(RuntimeError, 'in line details:'):
                _parse_lines_to_list([bad_line])


if __name__ == '__main__':
    unittest.main()
