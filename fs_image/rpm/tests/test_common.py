#!/usr/bin/env python3
import ast
import os
import subprocess
import sys
import tempfile
import unittest

from ..common import Path, create_ro, RpmShard, Checksum


_BAD_UTF = b'\xc3('


class TestCommon(unittest.TestCase):

    def test_path_basics(self):
        self.assertEqual(b'foo/bar', Path('foo') / 'bar')
        self.assertEqual(b'/foo/bar', b'/foo' / Path('bar'))
        self.assertEqual(b'/baz', b'/be/bop' / Path(b'/baz'))
        self.assertEqual(b'bom', Path('/bim/bom').basename())
        self.assertEqual(b'/bim', Path('/bim/bom').dirname())

    def test_bad_utf_is_bad(self):
        with self.assertRaises(UnicodeDecodeError):
            _BAD_UTF.decode()

    def test_path_decode(self):
        with tempfile.TemporaryDirectory() as td:
            bad_utf_path = Path(td) / _BAD_UTF
            self.assertTrue(bad_utf_path.endswith(b'/' + _BAD_UTF))
            with open(bad_utf_path, 'w'):
                pass
            res = subprocess.run([
                sys.executable, '-c', f'import os;print(os.listdir({repr(td)}))'
            ], stdout=subprocess.PIPE)
            # Path's handling of invalid UTF-8 matches the default for
            # Python3 when it gets such data from the filesystem.
            self.assertEqual(
                # Both evaluate to surrogate-escaped ['\udcc3('] plus a newline.
                repr([bad_utf_path.basename().decode()]) + '\n',
                res.stdout.decode(),
            )

    def test_path_from_argparse(self):
        res = subprocess.run([
            sys.executable, '-c', 'import sys;print(repr(sys.argv[1]))',
            _BAD_UTF,
        ], stdout=subprocess.PIPE)
        # Demangle non-UTF bytes in the same way that `sys.argv` mangles them.
        self.assertEqual(_BAD_UTF, Path.from_argparse(
            ast.literal_eval(res.stdout.rstrip(b'\n').decode())
        ))

    def test_create_ro(self):
        with tempfile.TemporaryDirectory() as td:
            with create_ro(Path(td) / 'hello_ro', 'w') as out_f:
                out_f.write('world_ro')
            with open(Path(td) / 'hello_rw', 'w') as out_f:
                out_f.write('world_rw')

            # `_create_ro` refuses to overwrite both RO and RW files.
            with self.assertRaises(FileExistsError):
                create_ro(Path(td) / 'hello_ro', 'w')
            with self.assertRaises(FileExistsError):
                create_ro(Path(td) / 'hello_rw', 'w')

            # Regular `open` can accidentelly clobber the RW, but not the RW.
            if os.geteuid() != 0:  # Root can clobber anything :/
                with self.assertRaises(PermissionError):
                    open(Path(td) / 'hello_ro', 'a')
            with open(Path(td) / 'hello_rw', 'a') as out_f:
                out_f.write(' -- appended')

            with open(Path(td) / 'hello_ro') as in_f:
                self.assertEqual('world_ro', in_f.read())
            with open(Path(td) / 'hello_rw') as in_f:
                self.assertEqual('world_rw -- appended', in_f.read())

    def test_rpm_shard(self):
        self.assertEqual(
            RpmShard(shard=3, modulo=7), RpmShard.from_string('3:7'),
        )

        class FakeRpm:
            def __init__(self, filename):
                self._filename = filename

            def filename(self):
                return self._filename

        self.assertEqual(
            [('foo', True), ('bar', False), ('foo', False), ('bar', True)],
            [
                (rpm, shard.in_shard(FakeRpm(rpm)))
                    for shard in [RpmShard(1, 7), RpmShard(2, 7)]
                        for rpm in ['foo', 'bar']
            ],
        )

    def test_checksum(self):
        cs = Checksum(algorithm='oops', hexdigest='dada')
        self.assertEqual('oops:dada', str(cs))
        self.assertEqual(cs, Checksum.from_string(str(cs)))
        for algo in ['sha1', 'sha']:
            h = Checksum(algo, 'ignored').hasher()
            h.update(b'banana')
            self.assertEqual(
                '250e77f12a5ab6972a0895d290c4792f0a326ea8', h.hexdigest(),
            )
