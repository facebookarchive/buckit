#!/usr/bin/env python3
import os
import shutil
import unittest
import urllib.parse

from ..common import temp_dir
from ..gpg_keys import snapshot_gpg_keys


class OpenUrlTestCase(unittest.TestCase):

    def test_snapshot_gpg_keys(self):
        with temp_dir() as td:
            hello_path = td / 'hello'
            with open(hello_path, 'w') as out_f:
                out_f.write('world')

            whitelist_dir = td / 'whitelist'
            os.mkdir(whitelist_dir)

            def try_snapshot(snapshot_dir):
                snapshot_gpg_keys(
                    key_urls=['file://' + urllib.parse.quote(hello_path)],
                    whitelist_dir=whitelist_dir,
                    snapshot_dir=snapshot_dir,
                )

            # The snapshot won't work until the key is correctly whitelisted.
            with temp_dir() as snap_dir, self.assertRaises(FileNotFoundError):
                try_snapshot(snap_dir)
            with open(whitelist_dir / 'hello', 'w') as out_f:
                out_f.write('wrong contents')
            with temp_dir() as snap_dir, self.assertRaises(AssertionError):
                try_snapshot(snap_dir)
            shutil.copy(hello_path, whitelist_dir)

            with temp_dir() as snapshot_dir:
                try_snapshot(snapshot_dir)
                self.assertEqual([b'gpg_keys'], os.listdir(snapshot_dir))
                self.assertEqual(
                    [b'hello'], os.listdir(snapshot_dir / 'gpg_keys'),
                )
                with open(snapshot_dir / 'gpg_keys/hello') as in_f:
                    self.assertEqual('world', in_f.read())
