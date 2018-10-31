#!/usr/bin/env python3
import tempfile
import unittest

from ..dep_graph import DependencyGraph
from ..items_for_features import gen_items_for_features

from . import sample_items as si


class ImageFeatureTestCase(unittest.TestCase):
    '''
    The main point of this test is to build the sample targets, and check
    that their outputs are correct. The install order check is incidental.
    '''

    def test_serialize_deserialize(self):
        root_feature_target = si.mangle(si.T_COPY_DIRS_TAR)
        self.assertIn(root_feature_target, si.TARGET_TO_PATH)
        self.assertEqual(
            {v for k, v in si.ID_TO_ITEM.items() if k != '/'},
            set(gen_items_for_features(
                [si.TARGET_TO_PATH[root_feature_target]],
                si.TARGET_TO_PATH,
                yum_from_repo_snapshot='/fake/yum',
            )),
        )
        # Fail if some target fails to resolve to a path
        with self.assertRaisesRegex(RuntimeError, f'{si.T_BASE}:[^ ]* not in'):
            list(gen_items_for_features(
                [si.TARGET_TO_PATH[root_feature_target]],
                target_to_path={},
                yum_from_repo_snapshot='/fake/yum',
            ))

    def test_install_order(self):
        dg = DependencyGraph(si.ID_TO_ITEM.values())
        phases = dg.ordered_phases()
        self.assertEqual([
            si.ID_TO_ITEM['/'],
            si.ID_TO_ITEM['.rpms/remove_if_exists/rpm-test-{carrot,milk}'],
            si.ID_TO_ITEM['.rpms/install/rpm-test-mice'],
        ], phases)
        with tempfile.TemporaryDirectory() as td:
            doi = list(dg.gen_dependency_order_items(td))
        self.assertEqual(set(si.ID_TO_ITEM.values()), set(doi + phases))
        self.assertEqual(
            len(si.ID_TO_ITEM),
            len(doi) + len(phases),
            msg='Duplicate items?',
        )
        id_to_idx = {
            k: doi.index(v)
                for k, v in si.ID_TO_ITEM.items()
                    if v not in phases
        }
        self.assertEqual(0, id_to_idx['foo/bar'])
        self.assertLess(
            id_to_idx['foo/borf/beep'], id_to_idx['foo/borf/hello_world']
        )


if __name__ == '__main__':
    unittest.main()
