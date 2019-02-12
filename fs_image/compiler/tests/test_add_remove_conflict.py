#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import unittest

from artifacts_dir import ensure_per_repo_artifacts_dir_exists
from btrfs_diff.tests.render_subvols import render_sendstream
from subvol_utils import Subvol
from volume_for_repo import get_volume_for_current_repo

from ..compiler import parse_args, build_image
from ..subvolume_on_disk import SubvolumeOnDisk


def _test_feature_target(feature_target):
    return '//fs_image/compiler/tests:' + feature_target + (
        '_IF_YOU_REFER_TO_THIS_RULE_YOUR_DEPENDENCIES_WILL_BE_BROKEN_'
        'SO_DO_NOT_DO_THIS_EVER_PLEASE_KTHXBAI'
    )


class AddRemoveConflictTestCase(unittest.TestCase):

    def setUp(self):
        lots_of_bytes = 1e8  # Our loopback is sparse, so just make it huge.
        self.volume_dir = get_volume_for_current_repo(
            lots_of_bytes, ensure_per_repo_artifacts_dir_exists(sys.argv[0]),
        )
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

    def _resource_path(self, name: str):
        return os.path.join(
            # This works even in @mode/opt because the test is a XAR
            os.path.dirname(__file__), 'data/' + name,
        )

    def _resource_subvol(self, name: str):
        with open(self._resource_path(name + '/layer.json')) as infile:
            return SubvolumeOnDisk.from_json_file(
                infile, os.path.join(self.volume_dir, 'targets'),
            )

    def test_check_layers(self):
        # The parent has a couple of directories.
        self.assertEqual(
            ['(Dir)', {
                'a': ['(Dir)', {'b': ['(Dir)', {}]}],
                'meta': ['(Dir)', {}],
            }],
            render_sendstream(Subvol(
                self._resource_subvol('parent').subvolume_path(),
                already_exists=True
            ).mark_readonly_and_get_sendstream()),
        )
        # The child is near-empty because the `remove_paths` cleaned it up.
        self.assertEqual(
            ['(Dir)', {'meta': ['(Dir)', {}]}],
            render_sendstream(Subvol(
                self._resource_subvol('child').subvolume_path(),
                already_exists=True
            ).mark_readonly_and_get_sendstream()),
        )

    def test_conflict(self):
        # Future: de-duplicate this with TempSubvolumes, perhaps?
        tmp_parent = os.path.join(self.volume_dir, 'tmp')
        try:
            os.mkdir(tmp_parent)
        except FileExistsError:
            pass
        # Removes get built before adds, so a conflict means nothing to remove
        with tempfile.TemporaryDirectory(dir=tmp_parent) as temp_subvol_dir, \
                self.assertRaisesRegex(AssertionError, 'Path does not exist'):
            try:
                # We cannot make this an `image.layer` target, since Buck
                # doesn't (yet) have a nice story for testing targets whose
                # builds are SUPPOSED to fail.
                build_image(parse_args([
                    '--subvolumes-dir', temp_subvol_dir,
                    '--subvolume-rel-path', 'SUBVOL',
                    '--child-layer-target', 'unused',
                    '--child-feature-json', self._resource_path('feature_both'),
                    '--child-dependencies',
                    _test_feature_target('feature_addremove_conflict_add'),
                    self._resource_path('feature_add'),
                    _test_feature_target('feature_addremove_conflict_remove'),
                    self._resource_path('feature_remove'),
                ]))
            finally:
                # Ignore error code in case something broke early in the test
                subprocess.run([
                    'sudo', 'btrfs', 'subvolume', 'delete',
                    os.path.join(temp_subvol_dir, 'SUBVOL'),
                ])
