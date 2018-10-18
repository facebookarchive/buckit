#!/usr/bin/env python3
import unittest

from ..dep_graph import gen_dependency_order_items
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
            )),
        )
        # Fail if some target fails to resolve to a path
        with self.assertRaisesRegex(RuntimeError, f'{si.T_BASE}:[^ ]* not in'):
            list(gen_items_for_features(
                [si.TARGET_TO_PATH[root_feature_target]],
                target_to_path={},
            ))

    def test_install_order(self):
        doi = list(gen_dependency_order_items(si.ID_TO_ITEM.values()))
        self.assertEqual(set(si.ID_TO_ITEM.values()), set(doi))
        self.assertEqual(len(si.ID_TO_ITEM), len(doi), msg='Duplicate items?')
        id_to_idx = {k: doi.index(v) for k, v in si.ID_TO_ITEM.items()}
        self.assertEqual(0, id_to_idx['/'])
        self.assertEqual(1, id_to_idx['foo/bar'])
        self.assertLess(
            id_to_idx['foo/borf/beep'], id_to_idx['foo/borf/hello_world']
        )


if __name__ == '__main__':
    unittest.main()
