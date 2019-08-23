#!/usr/bin/env python3
import copy
import os
import sys

from compiler.provides import ProvidesDirectory, ProvidesDoNotAccess
from compiler.tests.mock_subvolume_from_json_file import (
    TEST_SUBVOLS_DIR, mock_subvolume_from_json_file,
)
from tests.temp_subvolumes import TempSubvolumes

from ..make_dirs import MakeDirsItem
from ..parent_layer import (
    FilesystemRootItem, gen_parent_layer_items, ParentLayerItem,
)

from .common import (
    BaseItemTestCase, DUMMY_LAYER_OPTS, populate_temp_filesystem,
    render_subvol, temp_filesystem_provides,
)


class ParentLayerItemsTestCase(BaseItemTestCase):

    def test_filesystem_root(self):
        self._check_item(
            FilesystemRootItem(from_target='t'),
            {ProvidesDirectory(path='/'), ProvidesDoNotAccess(path='/meta')},
            set(),
        )
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

    def test_parent_layer_provides(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            parent = temp_subvolumes.create('parent')
            # Permit _populate_temp_filesystem to make writes.
            parent.run_as_root([
                'chown', '--no-dereference', f'{os.geteuid()}:{os.getegid()}',
                parent.path(),
            ])
            populate_temp_filesystem(parent.path().decode())
            for create_meta in [False, True]:
                # Check that we properly handle ignoring a /meta if it's present
                if create_meta:
                    parent.run_as_root(['mkdir', parent.path('meta')])
                self._check_item(
                    ParentLayerItem(
                        from_target='t', path=parent.path().decode(),
                    ),
                    temp_filesystem_provides() | {
                        ProvidesDirectory(path='/'),
                        ProvidesDoNotAccess(path='/meta'),
                    },
                    set(),
                )

    def test_parent_layer_builder(self):
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
                [ParentLayerItem(from_target='t', path=parent.path().decode())],
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

    def test_parent_layer_items(self):
        with mock_subvolume_from_json_file(self, path=None):
            self.assertEqual(
                [FilesystemRootItem(from_target='tgt')],
                list(gen_parent_layer_items('tgt', None, TEST_SUBVOLS_DIR)),
            )

        with mock_subvolume_from_json_file(self, path='potato') as json_file:
            self.assertEqual(
                [ParentLayerItem(from_target='T', path='potato')],
                list(gen_parent_layer_items('T', json_file, TEST_SUBVOLS_DIR)),
            )
