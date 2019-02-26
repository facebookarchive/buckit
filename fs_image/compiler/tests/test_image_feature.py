#!/usr/bin/env python3
import sys
import unittest

from tests.temp_subvolumes import TempSubvolumes

from ..dep_graph import DependencyGraph
from ..items import FilesystemRootItem, RemovePathItem, RpmActionItem
from ..items_for_features import gen_items_for_features

from . import sample_items as si


class ImageFeatureTestCase(unittest.TestCase):
    '''
    The main point of this test is to build the sample targets, and check
    that their outputs are correct. The install order check is incidental.
    '''

    def test_serialize_deserialize(self):
        root_feature_target = si.mangle(si.T_KITCHEN_SINK)
        self.assertIn(root_feature_target, si.TARGET_TO_PATH)
        self.assertEqual(
            {v for k, v in si.ID_TO_ITEM.items() if k != '/'},
            set(gen_items_for_features(
                exit_stack=None,  # unused, no `generator` TarballItems
                feature_paths=[si.TARGET_TO_PATH[root_feature_target]],
                target_to_path=si.TARGET_TO_PATH,
            )),
        )
        # Fail if some target fails to resolve to a path
        with self.assertRaisesRegex(RuntimeError, f'{si.T_BASE}:[^ ]* not in'):
            list(gen_items_for_features(
                exit_stack=None,  # unused, no `generator` TarballItems
                feature_paths=[si.TARGET_TO_PATH[root_feature_target]],
                target_to_path={},
            ))

    def test_install_order(self):
        dg = DependencyGraph(si.ID_TO_ITEM.values())
        builders_and_phases = list(dg.ordered_phases())
        self.assertEqual([
            (
                FilesystemRootItem.get_phase_builder,
                (si.ID_TO_ITEM['/'],),
            ),
            (
                RpmActionItem.get_phase_builder,
                (
                    si.ID_TO_ITEM['.rpms/remove_if_exists/rpm-test-carrot'],
                    si.ID_TO_ITEM['.rpms/remove_if_exists/rpm-test-milk'],
                ),
            ),
            (
                RpmActionItem.get_phase_builder,
                (si.ID_TO_ITEM['.rpms/install/rpm-test-mice'],),
            ),
            (
                RemovePathItem.get_phase_builder,
                (
                    si.ID_TO_ITEM['.remove_if_exists/path/to/remove'],
                    si.ID_TO_ITEM['.remove_assert_exists/path/to/remove'],
                    si.ID_TO_ITEM[
                        '.remove_assert_exists/another/path/to/remove'
                    ],
                ),
            ),
        ], builders_and_phases)
        phase_items = [i for _, items in builders_and_phases for i in items]
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('subvol')
            doi = list(dg.gen_dependency_order_items(subvol.path().decode()))
        self.assertEqual(set(si.ID_TO_ITEM.values()), set(doi + phase_items))
        self.assertEqual(
            len(si.ID_TO_ITEM),
            len(doi) + len(phase_items),
            msg='Duplicate items?',
        )
        id_to_idx = {
            k: doi.index(v)
                for k, v in si.ID_TO_ITEM.items()
                    if v not in phase_items
        }
        # The 2 mounts are not ordered in any way with respect to the
        # `foo/bar` tree, so any of these 3 can be the first.
        mount_idxs = sorted([id_to_idx['host_etc'], id_to_idx['meownt']])
        if mount_idxs == [0, 1]:
            self.assertEqual(2, id_to_idx['foo/bar'])
        elif 0 in mount_idxs:
            self.assertEqual(1, id_to_idx['foo/bar'])
        else:
            self.assertEqual(0, id_to_idx['foo/bar'])
        self.assertLess(
            id_to_idx['foo/borf/beep'], id_to_idx['foo/borf/hello_world']
        )


if __name__ == '__main__':
    unittest.main()
