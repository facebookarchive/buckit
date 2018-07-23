#!/usr/bin/env python3
import os
import sys
import unittest

from contextlib import contextmanager

from artifacts_dir import ensure_per_repo_artifacts_dir_exists
from volume_for_repo import get_volume_for_current_repo

from ..subvolume_on_disk import SubvolumeOnDisk

# Our target names are too long :(
T_BASE = (
    '//tools/build/buck/infra_macros/macro_lib/convert/container_image/'
    'compiler/tests'
)
T_HELLO_WORLD = f'{T_BASE}:hello_world_base'
T_PARENT = f'{T_BASE}:parent_layer'
T_CHILD = f'{T_BASE}:child_layer'


TARGET_ENV_VAR_PREFIX = 'test_image_layer_path_to_'
TARGET_TO_FILENAME = {
    target[len(TARGET_ENV_VAR_PREFIX):]: path
        for target, path in os.environ.items()
            if target.startswith(TARGET_ENV_VAR_PREFIX)
}


class ImageLayerTestCase(unittest.TestCase):

    def setUp(self):
        self.subvolumes_dir = os.path.join(
            get_volume_for_current_repo(
                1e8, ensure_per_repo_artifacts_dir_exists(sys.argv[0]),
            ),
            'targets',
        )

    @contextmanager
    def target_subvol(self, target):
        with self.subTest(target):
            with open(TARGET_TO_FILENAME[target]) as infile:
                yield SubvolumeOnDisk.from_json_file(
                    infile, self.subvolumes_dir,
                )

    def _check_hello(self, subvol_path):
        with open(os.path.join(subvol_path, 'hello_world')) as hello:
            self.assertEqual('', hello.read())

    def _check_parent(self, subvol_path):
        self._check_hello(subvol_path)
        # :parent_layer
        for path in [
            'foo/bar/hello_world.tar', 'foo/bar/even_more_hello_world.tar',
        ]:
            self.assertTrue(
                os.path.isfile(os.path.join(subvol_path, path)),
                path,
            )
        # :feature_dirs not tested by :parent_layer
        self.assertTrue(
            os.path.isdir(os.path.join(subvol_path, 'foo/bar/baz')),
        )

    def _check_child(self, subvol_path):
        self._check_parent(subvol_path)
        for path in [
            # :feature_tar
            'foo/borf/hello_world',
            'foo/hello_world',
            # :child_layer
            'foo/extracted_hello/hello_world',
            'foo/more_extracted_hello/hello_world',
        ]:
            self.assertTrue(os.path.isfile(os.path.join(subvol_path, path)))

    def test_hello_world_base(self):
        # Future: replace these checks by a more comprehensive test of the
        # image's data & metadata using our `btrfs_diff` library.
        with self.target_subvol('hello_world_base') as sod:
            self._check_hello(sod.subvolume_path())
        with self.target_subvol('parent_layer') as sod:
            self._check_parent(sod.subvolume_path())
        with self.target_subvol('child_layer') as sod:
            self._check_child(sod.subvolume_path())
