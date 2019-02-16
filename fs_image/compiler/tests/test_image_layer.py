#!/usr/bin/env python3
import json
import os
import sys
import unittest

from contextlib import contextmanager

from artifacts_dir import ensure_per_repo_artifacts_dir_exists
from btrfs_diff.tests.render_subvols import render_sendstream
from btrfs_diff.tests.demo_sendstreams_expected import render_demo_subvols
from subvol_utils import Subvol
from volume_for_repo import get_volume_for_current_repo

from ..subvolume_on_disk import SubvolumeOnDisk


TARGET_ENV_VAR_PREFIX = 'test_image_layer_path_to_'
TARGET_TO_PATH = {
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
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

    @contextmanager
    def target_subvol(self, target):
        with self.subTest(target):
            # The mount configuration is very uniform, so we can check it here.
            with open(TARGET_TO_PATH[target] + '/mountconfig.json') as infile:
                self.assertEqual({
                    'build_source': {
                        'type': 'layer',
                        'target': '//fs_image/compiler/tests:' + target,
                    },
                }, json.load(infile))
            with open(TARGET_TO_PATH[target] + '/layer.json') as infile:
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
            'usr/share/rpm_test/hello_world.tar',
            'foo/bar/even_more_hello_world.tar',
        ]:
            self.assertTrue(
                os.path.isfile(os.path.join(subvol_path, path)),
                path,
            )
        # :feature_dirs not tested by :parent_layer
        self.assertTrue(
            os.path.isdir(os.path.join(subvol_path, 'foo/bar/baz')),
        )
        # :hello_world_base was mounted here
        self.assertTrue(os.path.exists(
            os.path.join(subvol_path, 'mounted_hello/hello_world')
        ))

        # :feature_symlinks
        for source, dest in [
            ('foo/bar', 'foo/fighter'),
            ('foo/bar', 'foo/face'),
            ('foo/bar', 'foo/bar/baz/bar'),
            ('foo/hello_world.tar', 'foo/symlink_to_hello_world.tar'),
        ]:
            self.assertTrue(
                os.path.exists(os.path.join(subvol_path, source)),
                source
            )

            self.assertTrue(
                os.path.islink(os.path.join(subvol_path, dest)),
                dest
            )

            self.assertEqual(
                os.path.join('/', source),
                os.readlink(os.path.join(subvol_path, dest))
            )

    def _check_child(self, subvol_path):
        self._check_parent(subvol_path)
        for path in [
            # :feature_tar_and_rpms
            'foo/borf/hello_world',
            'foo/hello_world',
            'usr/share/rpm_test/mice.txt',
            # :child_layer
            'foo/extracted_hello/hello_world',
            'foo/more_extracted_hello/hello_world',
        ]:
            self.assertTrue(os.path.isfile(os.path.join(subvol_path, path)))
        for path in [
            # :feature_tar_and_rpms ensures these are absent
            'usr/share/rpm_test/carrot.txt',
            'usr/share/rpm_test/milk.txt',
        ]:
            self.assertFalse(os.path.exists(os.path.join(subvol_path, path)))

    def test_image_layer_targets(self):
        # Future: replace these checks by a more comprehensive test of the
        # image's data & metadata using our `btrfs_diff` library.
        with self.target_subvol('hello_world_base') as sod:
            self._check_hello(sod.subvolume_path())
        with self.target_subvol('parent_layer') as sod:
            self._check_parent(sod.subvolume_path())
            # Cannot check this in `_check_parent`, since that gets called
            # by `_check_child`, but the RPM gets removed in the child.
            self.assertTrue(os.path.isfile(os.path.join(
                sod.subvolume_path(), 'usr/share/rpm_test/carrot.txt',
            )))
        with self.target_subvol('child_layer') as sod:
            self._check_child(sod.subvolume_path())

    def test_layer_from_demo_sendstreams(self):
        # `btrfs_diff.demo_sendstream` produces a subvolume send-stream with
        # fairly thorough coverage of filesystem features.  This test grabs
        # that send-stream, receives it into an `image_layer`, and validates
        # that the send-stream of the **received** volume has the same
        # rendering as the original send-stream was supposed to have.
        #
        # In other words, besides testing `image_layer`'s `from_sendstream`,
        # this is also a test of idempotence for btrfs send+receive.
        #
        # Notes:
        #  - `compiler/tests/TARGETS` explains why `mutate_ops` is not here.
        #  - Currently, `mutate_ops` also uses `--no-data`, which would
        #    break this test of idempotence.
        for op in ['create_ops']:
            with self.target_subvol(op) as sod:
                self.assertEqual(
                    render_demo_subvols(**{op: True}),
                    render_sendstream(
                        Subvol(sod.subvolume_path(), already_exists=True)
                            .mark_readonly_and_get_sendstream(),
                    ),
                )
