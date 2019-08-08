#!/usr/bin/env python3
import ast
import errno
import os
import subprocess
import sys
import tempfile
import time
import unittest

from ..common import (
    Checksum, create_ro, log as common_log, Path, temp_dir,
    populate_temp_dir_and_rename, retry_fn, RpmShard,
)


_BAD_UTF = b'\xc3('


class TestCommon(unittest.TestCase):

    def test_path_basics(self):
        self.assertEqual(b'foo/bar', Path('foo') / 'bar')
        self.assertEqual(b'/foo/bar', b'/foo' / Path('bar'))
        self.assertEqual(b'/baz', b'/be/bop' / Path(b'/baz'))
        self.assertEqual('file:///a%2Cb', Path('/a,b').file_url())
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
        with temp_dir() as td:
            with create_ro(td / 'hello_ro', 'w') as out_f:
                out_f.write('world_ro')
            with open(td / 'hello_rw', 'w') as out_f:
                out_f.write('world_rw')

            # `_create_ro` refuses to overwrite both RO and RW files.
            with self.assertRaises(FileExistsError):
                create_ro(td / 'hello_ro', 'w')
            with self.assertRaises(FileExistsError):
                create_ro(td / 'hello_rw', 'w')

            # Regular `open` can accidentelly clobber the RW, but not the RW.
            if os.geteuid() != 0:  # Root can clobber anything :/
                with self.assertRaises(PermissionError):
                    open(td / 'hello_ro', 'a')
            with open(td / 'hello_rw', 'a') as out_f:
                out_f.write(' -- appended')

            with open(td / 'hello_ro') as in_f:
                self.assertEqual('world_ro', in_f.read())
            with open(td / 'hello_rw') as in_f:
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

    def _check_has_one_file(self, dir_path, filename, contents):
        self.assertEqual([filename.encode()], os.listdir(dir_path))
        with open(dir_path / filename) as in_f:
            self.assertEqual(contents, in_f.read())

    def test_populate_temp_dir_and_rename(self):
        with temp_dir() as td:
            # Create and populate "foo"
            foo_path = td / 'foo'
            with populate_temp_dir_and_rename(foo_path) as td2:
                self.assertTrue(td2.startswith(td + b'/'))
                self.assertEqual(td2, td / td2.basename())
                self.assertNotEqual(td2.basename(), 'foo')
                with create_ro(td2 / 'hello', 'w') as out_f:
                    out_f.write('world')
            self._check_has_one_file(foo_path, 'hello', 'world')

            # Fail to overwrite
            with self.assertRaises(OSError) as ex_ctx:
                with populate_temp_dir_and_rename(foo_path):
                    pass  # Try to overwrite with empty.
            # Different kernels return different error codes :/
            self.assertIn(ex_ctx.exception.errno, [errno.ENOTEMPTY, errno.EEXIST])
            self._check_has_one_file(foo_path, 'hello', 'world')  # No change

            # Force-overwrite
            with populate_temp_dir_and_rename(foo_path, overwrite=True) as td2:
                with create_ro(td2 / 'farewell', 'w') as out_f:
                    out_f.write('arms')
            self._check_has_one_file(foo_path, 'farewell', 'arms')

    def test_retry_fn(self):

        class Retriable:
            def __init__(self, attempts_to_fail=0):
                self.attempts = 0
                self.first_success_attempt = attempts_to_fail + 1

            def run(self):
                self.attempts += 1
                if self.attempts >= self.first_success_attempt:
                    return self.attempts
                raise RuntimeError(self.attempts)

        self.assertEqual(1, retry_fn(
            Retriable().run, delays=[], what='succeeds immediately'
        ))

        # Check log messages, and ensure that delays add up as expected
        start_time = time.time()
        with self.assertLogs(common_log) as log_ctx:
            self.assertEqual(4, retry_fn(
                Retriable(3).run, delays=[0, 0.1, 0.2], what='succeeds on try 4'
            ))
        self.assertTrue(any(
            '\n[Retry 3 of 3] succeeds on try 4 -- waiting 0.2 seconds.\n' in o
                for o in log_ctx.output
        ))
        self.assertGreater(time.time() - start_time, 0.3)

        # Check running out of retries
        with self.assertLogs(common_log) as log_ctx, \
                self.assertRaises(RuntimeError) as ex_ctx:
            retry_fn(Retriable(100).run, delays=[0] * 7, what='never succeeds')
        self.assertTrue(any(
            '\n[Retry 7 of 7] never succeeds -- waiting 0 seconds.\n' in o
                for o in log_ctx.output
        ))
        self.assertEqual((8,), ex_ctx.exception.args)
