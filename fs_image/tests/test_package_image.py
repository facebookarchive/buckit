#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

from contextlib import contextmanager
from typing import Iterator

from artifacts_dir import ensure_per_repo_artifacts_dir_exists
from btrfs_diff.tests.render_subvols import render_sendstream
from package_image import package_image, Format
from volume_for_repo import get_volume_for_current_repo


class PackageImageTestCase(unittest.TestCase):

    def setUp(self):
        self.subvolumes_dir = os.path.join(
            get_volume_for_current_repo(
                1e8, ensure_per_repo_artifacts_dir_exists(sys.argv[0]),
            ),
            'targets',
        )
        # Works in @mode/opt since the files of interest are baked into the XAR
        self.my_dir = os.path.dirname(__file__)

    @contextmanager
    def _package_image(self, json_path: str, format: str) -> Iterator[str]:
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, 'sendstream')
            package_image([
                '--subvolumes-dir', self.subvolumes_dir,
                '--subvolume-json', json_path,
                '--format', format,
                '--output-path', out_path,
            ])
            yield out_path

    def _sibling_path(self, rel_path: str):
        return os.path.join(self.my_dir, rel_path)

    def _assert_sendstream_files_equal(self, path1: str, path2: str):
        renders = []
        for path in [path1, path2]:
            with open(self._sibling_path(path), 'rb') as infile:
                renders.append(render_sendstream(infile.read()))
        self.assertEqual(*renders)

    # This tests `image_package.py` by consuming its output.
    def test_packaged_sendstream_matches_original(self):
        self._assert_sendstream_files_equal(
            self._sibling_path('create_ops-original.sendstream'),
            self._sibling_path('create_ops.sendstream'),
        )

    def test_package_image_as_sendstream(self):
        with self._package_image(
            self._sibling_path('create_ops.json'), 'sendstream',
        ) as out_path:
            self._assert_sendstream_files_equal(
                self._sibling_path('create_ops-original.sendstream'),
                out_path,
            )

    def test_format_name_collision(self):
        with self.assertRaisesRegex(AssertionError, 'share format_name'):

            class BadFormat(Format, format_name='sendstream'):
                pass
