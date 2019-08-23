#!/usr/bin/env python3
from compiler.provides import ProvidesDirectory
from compiler.requires import require_directory

from ..common import PhaseOrder
from ..install_file import InstallFileItem
from ..make_dirs import MakeDirsItem
from ..parent_layer import (
    FilesystemRootItem, ParentLayerItem,
)
from ..rpm_action import RpmAction, RpmActionItem

from .common import BaseItemTestCase


class ItemsCommonTestCase(BaseItemTestCase):

    def test_phase_orders(self):
        self.assertIs(
            None,
            InstallFileItem(
                from_target='t', source={'source': 'a'}, dest='b',
                is_executable_=False,
            ).phase_order(),
        )
        self.assertEqual(
            PhaseOrder.PARENT_LAYER,
            FilesystemRootItem(from_target='t').phase_order(),
        )
        self.assertEqual(
            PhaseOrder.PARENT_LAYER,
            ParentLayerItem(from_target='t', path='unused').phase_order(),
        )
        self.assertEqual(PhaseOrder.RPM_INSTALL, RpmActionItem(
            from_target='t', name='n', action=RpmAction.install,
        ).phase_order())
        self.assertEqual(PhaseOrder.RPM_REMOVE, RpmActionItem(
            from_target='t', name='n', action=RpmAction.remove_if_exists,
        ).phase_order())

    def test_enforce_no_parent_dir(self):
        with self.assertRaisesRegex(AssertionError, r'cannot start with \.\.'):
            InstallFileItem(
                from_target='t', source={'source': 'a'}, dest='a/../../b',
                is_executable_=False,
            )

    def test_stat_options(self):
        self._check_item(
            MakeDirsItem(
                from_target='t',
                into_dir='x',
                path_to_make='y/z',
                mode=0o733,
                user_group='cat:dog',
            ),
            {ProvidesDirectory(path='x/y'), ProvidesDirectory(path='x/y/z')},
            {require_directory('x')},
        )
