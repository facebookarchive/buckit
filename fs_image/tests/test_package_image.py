#!/usr/bin/env python3
import os
import stat
import subprocess
import sys
import tempfile
import unittest

from contextlib import contextmanager
from typing import Iterator

from btrfs_diff.tests.render_subvols import render_sendstream
from find_built_subvol import subvolumes_dir
from package_image import package_image, Format
from unshare import Namespace, nsenter_as_root, Unshare


class PackageImageTestCase(unittest.TestCase):

    def setUp(self):
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

        self.subvolumes_dir = subvolumes_dir(sys.argv[0])
        # Works in @mode/opt since the files of interest are baked into the XAR
        self.my_dir = os.path.dirname(__file__)

    @contextmanager
    def _package_image(
        self,
        json_path: str,
        format: str,
        rw_subvolume: bool = False
    ) -> Iterator[str]:
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, format)
            args = [
                '--subvolumes-dir', self.subvolumes_dir,
                '--subvolume-json', json_path,
                '--format', format,
                '--output-path', out_path,
            ]
            if rw_subvolume:
                args.append('--rw-subvolume')
            package_image(args)
            yield out_path

    def _sibling_path(self, rel_path: str):
        return os.path.join(self.my_dir, rel_path)

    def _assert_sendstream_files_equal(self, path1: str, path2: str):
        renders = []
        for path in [path1, path2]:
            if path.endswith('.zst'):
                data = subprocess.check_output(
                    ['zstd', '--decompress', '--stdout', path]
                )
            else:
                with open(path, 'rb') as infile:
                    data = infile.read()
            renders.append(render_sendstream(data))

        self.assertEqual(*renders)

    # This tests `image_package.bzl` by consuming its output.
    def test_packaged_sendstream_matches_original(self):
        self._assert_sendstream_files_equal(
            self._sibling_path('create_ops-original.sendstream'),
            self._sibling_path('create_ops.sendstream'),
        )

    def test_package_image_as_sendstream(self):
        for format in ['sendstream', 'sendstream.zst']:
            with self._package_image(
                self._sibling_path('create_ops.layer/layer.json'), format,
            ) as out_path:
                self._assert_sendstream_files_equal(
                    self._sibling_path('create_ops-original.sendstream'),
                    out_path,
                )

    def test_package_image_as_btrfs_loopback(self):
        with self._package_image(
            self._sibling_path('create_ops.layer/layer.json'), 'btrfs',
        ) as out_path, \
                Unshare([Namespace.MOUNT, Namespace.PID]) as unshare, \
                tempfile.TemporaryDirectory() as mount_dir, \
                tempfile.NamedTemporaryFile() as temp_sendstream:
            # Future: use a LoopbackMount object here once that's checked in.
            subprocess.check_call(nsenter_as_root(
                unshare, 'mount', '-t', 'btrfs', '-o', 'loop,discard,nobarrier',
                out_path, mount_dir,
            ))
            try:
                # Future: Once I have FD, this should become:
                # Subvol(
                #     os.path.join(mount_dir.fd_path(), 'create_ops'),
                #     already_exists=True,
                # ).mark_readonly_and_write_sendstream_to_file(temp_sendstream)
                # temp_sendstream.flush()
                subprocess.check_call(nsenter_as_root(
                    unshare, 'btrfs', 'send', '-f', temp_sendstream.name,
                    os.path.join(mount_dir, 'create_ops'),
                ))
                self._assert_sendstream_files_equal(
                    self._sibling_path('create_ops-original.sendstream'),
                    temp_sendstream.name,
                )
            finally:
                nsenter_as_root(unshare, 'umount', mount_dir)

    def test_package_image_as_btrfs_loopback_writable(self):
        with self._package_image(
            self._sibling_path('create_ops.layer/layer.json'),
            'btrfs',
            rw_subvolume=True,
        ) as out_path, \
                Unshare([Namespace.MOUNT, Namespace.PID]) as unshare, \
                tempfile.TemporaryDirectory() as mount_dir:
            os.chmod(
                out_path,
                stat.S_IMODE(os.stat(out_path).st_mode)
                | (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
            )
            subprocess.check_call(nsenter_as_root(
                unshare, 'mount', '-t', 'btrfs', '-o', 'loop,discard,nobarrier',
                out_path, mount_dir,
            ))
            try:
                subprocess.check_call(nsenter_as_root(
                    unshare, 'touch', os.path.join(mount_dir,
                                                   'create_ops',
                                                   'foo'),
                ))
            finally:
                nsenter_as_root(unshare, 'umount', mount_dir)

    def test_format_name_collision(self):
        with self.assertRaisesRegex(AssertionError, 'share format_name'):

            class BadFormat(Format, format_name='sendstream'):
                pass
