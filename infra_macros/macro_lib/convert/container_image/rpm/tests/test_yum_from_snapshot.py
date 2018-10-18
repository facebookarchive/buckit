#!/usr/bin/env python3
import os
import tempfile
import subprocess
import unittest

from ..common import init_logging, Path
from .yum_from_test_snapshot import yum_from_test_snapshot


init_logging()


class YumFromSnapshotTestCase(unittest.TestCase):

    def test_verify_contents_of_install_from_snapshot(self):
        install_root = Path(tempfile.mkdtemp())
        try:
            yum_from_test_snapshot(install_root, [
                'install', '--assumeyes', 'rpm-test-carrot', 'rpm-test-mice',
            ])

            # Remove known content so we can check there is nothing else.
            remove = []

            # Check that the RPMs installed their payload.
            for path, content in [
                ('mice.txt', 'mice 0.1 a\n'),
                ('carrot.txt', 'carrot 2 rc0\n'),
            ]:
                remove.append(install_root / 'usr/share/rpm_test' / path)
                with open(remove[-1]) as f:
                    self.assertEqual(content, f.read())

            # Yum also writes some indexes & metadata.
            for path in ['var/lib/yum', 'var/lib/rpm', 'var/cache/yum']:
                remove.append(install_root / path)
                self.assertTrue(os.path.isdir(remove[-1]))
            remove.append(install_root / 'var/log/yum.log')
            self.assertTrue(os.path.exists(remove[-1]))

            # Check that the above list of paths is complete.
            for path in remove:
                # We're running rm -rf as `root`, better be careful.
                self.assertTrue(path.startswith(install_root))
                # Most files are owned by root, so the sudo is needed.
                subprocess.run(['sudo', 'rm', '-rf', path], check=True)
            subprocess.run([
                'sudo', 'rmdir',
                'usr/share/rpm_test', 'usr/share', 'usr',
                'var/lib', 'var/cache', 'var/log', 'var',
            ], check=True, cwd=install_root)
            self.assertEqual([], os.listdir(install_root))
        finally:
            assert install_root != '/'
            # Courtesy of `yum`, the `install_root` is now owned by root.
            subprocess.run(['sudo', 'rm', '-rf', install_root], check=True)
