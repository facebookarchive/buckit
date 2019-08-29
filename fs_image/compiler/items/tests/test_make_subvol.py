#!/usr/bin/env python3
import copy
import sys

from tests.temp_subvolumes import TempSubvolumes

from ..make_dirs import MakeDirsItem
from ..make_subvol import FilesystemRootItem, ParentLayerItem

from .common import (
    BaseItemTestCase, DUMMY_LAYER_OPTS, populate_temp_filesystem,
    render_subvol, temp_filesystem_provides,
)


class MakeSubvolItemsTestCase(BaseItemTestCase):

    def test_filesystem_root(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.caller_will_create('fs-root')
            FilesystemRootItem.get_phase_builder(
                [FilesystemRootItem(from_target='t')], DUMMY_LAYER_OPTS,
            )(subvol)
            self.assertEqual(
                ['(Dir)', {'meta': ['(Dir)', {'private': ['(Dir)', {
                    'opts': ['(Dir)', {
                        'artifacts_may_require_repo': ['(File d2)'],
                    }],
                }]}]}], render_subvol(subvol),
            )

    def test_parent_layer(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            parent = temp_subvolumes.create('parent')
            MakeDirsItem(
                from_target='t', into_dir='/', path_to_make='a/b',
            ).build(parent, DUMMY_LAYER_OPTS)
            parent_content = ['(Dir)', {'a': ['(Dir)', {'b': ['(Dir)', {}]}]}]
            self.assertEqual(parent_content, render_subvol(parent))

            # Take a snapshot and add one more directory.
            child = temp_subvolumes.caller_will_create('child')
            ParentLayerItem.get_phase_builder(
                [ParentLayerItem(from_target='t', subvol=parent)],
                DUMMY_LAYER_OPTS,
            )(child)
            MakeDirsItem(
                from_target='t', into_dir='a', path_to_make='c',
            ).build(child, DUMMY_LAYER_OPTS)

            # The parent is unchanged.
            self.assertEqual(parent_content, render_subvol(parent))
            child_content = copy.deepcopy(parent_content)
            child_content[1]['a'][1]['c'] = ['(Dir)', {}]
            # Since the parent lacked a /meta, the child added it.
            child_content[1]['meta'] = ['(Dir)', {'private': ['(Dir)', {
                'opts': ['(Dir)', {'artifacts_may_require_repo': ['(File d2)']}]
            }]}]
            self.assertEqual(child_content, render_subvol(child))
