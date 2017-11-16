#!/usr/bin/env python3
import os
import unittest

from dep_graph import dependency_order_items
from items import CopyFileItem, MakeDirsItem, TarballItem, FilesystemRootItem
from items_for_features import gen_items_for_features


# Our target names are too long :(
T_BASE = (
    '//tools/build/buck/infra_macros/macro_lib/convert/container_image/'
    'compiler/tests'
)
# Use the "debug", human-readable forms of the image_feature targets here,
# since that's what we are testing.
T_DIRS = f'{T_BASE}:feature_dirs'
T_TAR = f'{T_BASE}:feature_tar'
T_COPY_DIRS_TAR = f'{T_BASE}:feature_copy_dirs_tar'
T_HELLO_WORLD_TAR = f'{T_BASE}:hello_world.tar'

TARGET_ENV_VAR_PREFIX = 'test_image_feature_path_to_'
TARGET_TO_FILENAME = {
    '{}:{}'.format(T_BASE, target[len(TARGET_ENV_VAR_PREFIX):]): path
        for target, path in os.environ.items()
            if target.startswith(TARGET_ENV_VAR_PREFIX)
}
assert T_HELLO_WORLD_TAR in TARGET_TO_FILENAME


# This should be a faithful transcription of the `image_feature`
# specifications in `test/TARGETS`.  The IDs currently have no semantics,
# existing only to give names to specific items.
ID_TO_ITEM = {
    '/': FilesystemRootItem(from_target=None),
    'foo/bar': MakeDirsItem(
        from_target=T_DIRS, into_dir='/', path_to_make='/foo/bar'
    ),
    'foo/bar/baz': MakeDirsItem(
        from_target=T_DIRS, into_dir='/foo/bar', path_to_make='baz'
    ),
    'foo/borf/beep': MakeDirsItem(
        from_target=T_DIRS,
        into_dir='/foo',
        path_to_make='borf/beep',
        user='uuu',
        group='ggg',
        mode='mmm',
    ),
    'foo/bar/hello_world.tar': CopyFileItem(
        from_target=T_COPY_DIRS_TAR,
        source=TARGET_TO_FILENAME[T_HELLO_WORLD_TAR],
        dest='/foo/bar/',
    ),
    'foo/bar/hello_world_again.tar': CopyFileItem(
        from_target=T_COPY_DIRS_TAR,
        source=TARGET_TO_FILENAME[T_HELLO_WORLD_TAR],
        dest='/foo/bar/hello_world_again.tar',
        group='nobody',
    ),
    'foo/borf/hello_world': TarballItem(
        from_target=T_TAR,
        tarball=TARGET_TO_FILENAME[T_HELLO_WORLD_TAR],
        into_dir='foo/borf',
    ),
    'foo/hello_world': TarballItem(
        from_target=T_TAR,
        tarball=TARGET_TO_FILENAME[T_HELLO_WORLD_TAR],
        into_dir='foo',
    ),
}


class ImageFeatureTestCase(unittest.TestCase):

    def test_serialize_deserialize(self):
        root_feature_target = T_COPY_DIRS_TAR + (
            '_IF_YOU_REFER_TO_THIS_RULE_YOUR_DEPENDENCIES_WILL_BE_BROKEN_'
            'SO_DO_NOT_DO_THIS_EVER_PLEASE_KTHXBAI'
        )
        self.assertIn(root_feature_target, TARGET_TO_FILENAME)
        self.assertEqual(
            {v for k, v in ID_TO_ITEM.items() if k != '/'},
            set(gen_items_for_features(
                [TARGET_TO_FILENAME[root_feature_target]], TARGET_TO_FILENAME
            )),
        )

    def test_install_order(self):
        doi = list(dependency_order_items(ID_TO_ITEM.values()))
        self.assertEqual(set(ID_TO_ITEM.values()), set(doi))
        self.assertEqual(len(ID_TO_ITEM), len(doi), msg='Duplicate items?')
        id_to_idx = {k: doi.index(v) for k, v in ID_TO_ITEM.items()}
        self.assertEqual(0, id_to_idx['/'])
        self.assertEqual(1, id_to_idx['foo/bar'])
        self.assertLess(
            id_to_idx['foo/borf/beep'], id_to_idx['foo/borf/hello_world']
        )
