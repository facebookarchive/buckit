#!/usr/bin/env python3
import itertools
import os
import subprocess
import tempfile
import unittest
import unittest.mock

import subvol_utils

from ..compiler import parse_args, build_image, LayerOpts
from .. import subvolume_on_disk as svod

from . import sample_items as si
from .mock_subvolume_from_json_file import (
    TEST_SUBVOLS_DIR, mock_subvolume_from_json_file,
)

_orig_btrfs_get_volume_props = svod._btrfs_get_volume_props
FAKE_SUBVOL = 'FAKE_SUBVOL'

def _subvol_mock_lexists_is_btrfs_and_run_as_root(fn):
    '''
    The purpose of these mocks is to run the compiler while recording
    what commands we WOULD HAVE run on the subvolume.  This is possible
    because all subvolume mutations are supposed to go through
    `Subvol.run_as_root`.  This lets our tests assert that the
    expected operations would have been executed.
    '''
    fn = unittest.mock.patch.object(os.path, 'lexists')(fn)
    fn = unittest.mock.patch.object(subvol_utils, '_path_is_btrfs_subvol')(fn)
    fn = unittest.mock.patch.object(subvol_utils.Subvol, 'run_as_root')(fn)
    return fn


_FIND_ARGS = [
    'find', '-P', f'{TEST_SUBVOLS_DIR}/{FAKE_SUBVOL}', '-printf', '%y %p\\0',
]


def _run_as_root(args, **kwargs):
    '''
    DependencyGraph adds a ParentLayerItem to traverse the subvolume, as
    modified by the phases. This ensures the traversal produces a subvol /
    '''
    if args[0] == 'find':
        assert args == _FIND_ARGS, args
        ret = unittest.mock.Mock()
        ret.stdout = f'd {TEST_SUBVOLS_DIR}/{FAKE_SUBVOL}\0'.encode()
        return ret


def _os_path_lexists(path):
    '''
    This ugly mock exists because I don't want to set up a fake subvolume,
    from which the `sample_items` `RemovePathItem`s can remove their files.
    '''
    if path.endswith(b'/to/remove'):
        return True
    assert 'AFAIK, os.path.lexists is only used by the `RemovePathItem` tests'


def _btrfs_get_volume_props(subvol_path):
    if subvol_path == os.path.join(TEST_SUBVOLS_DIR, FAKE_SUBVOL):
        # We don't have an actual btrfs subvolume, so make up a UUID.
        return {'UUID': 'fake uuid', 'Parent UUID': None}
    return _orig_btrfs_get_volume_props(subvol_path)


class CompilerTestCase(unittest.TestCase):

    def setUp(self):
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

        # This works @mode/opt since the yum binary is baked into our PAR
        self.yum_path = os.path.join(
            os.path.dirname(__file__), 'yum-from-test-snapshot',
        )

    @_subvol_mock_lexists_is_btrfs_and_run_as_root
    @unittest.mock.patch.object(svod, '_btrfs_get_volume_props')
    def _compile(
        self, args, btrfs_get_volume_props, lexists, is_btrfs, run_as_root,
    ):
        lexists.side_effect = _os_path_lexists
        run_as_root.side_effect = _run_as_root
        btrfs_get_volume_props.side_effect = _btrfs_get_volume_props
        # Since we're not making subvolumes, we need this so that
        # `Subvolume(..., already_exists=True)` will work.
        is_btrfs.return_value = True
        return build_image(parse_args([
            '--subvolumes-dir', TEST_SUBVOLS_DIR,
            '--subvolume-rel-path', FAKE_SUBVOL,
            '--yum-from-repo-snapshot', self.yum_path,
            '--child-layer-target', 'CHILD_TARGET',
            '--child-feature-json',
                si.TARGET_TO_PATH[si.mangle(si.T_KITCHEN_SINK)],
        ] + args)), run_as_root.call_args_list

    def test_child_dependency_errors(self):
        with self.assertRaisesRegex(
            RuntimeError, 'Odd-length --child-dependencies '
        ):
            self._compile(['--child-dependencies', 'foo'])

        # Our T_KITCHEN_SINK feature does have dependencies
        with self.assertRaisesRegex(
            RuntimeError, f'{si.T_BASE}:[^ ]* not in {{}}',
        ):
            self._compile([])

    def _compiler_run_as_root_calls(self, *, parent_args):
        '''
        Invoke the compiler on the targets from the "sample_items" test
        example, and ensure that the commands that the compiler would run
        are exactly the same ones that correspond to the expected
        `ImageItems`.

        In other words, these test assert that the compiler would run the
        right commands, without verifying their sequencing.  That is OK,
        since the dependency sort has its own unit test, and moreover
        `test_image_layer.py` does an end-to-end test that validates the
        final state of a compiled, live subvolume.
        '''
        res, run_as_root_calls = self._compile([
            *parent_args,
            '--child-dependencies',
            *itertools.chain.from_iterable(si.TARGET_TO_PATH.items()),
        ])
        self.assertEqual(svod.SubvolumeOnDisk(**{
            svod._BTRFS_UUID: 'fake uuid',
            svod._BTRFS_PARENT_UUID: None,
            svod._HOSTNAME: 'fake host',
            svod._SUBVOLUMES_BASE_DIR: TEST_SUBVOLS_DIR,
            svod._SUBVOLUME_REL_PATH: FAKE_SUBVOL,
        }), res._replace(**{svod._HOSTNAME: 'fake host'}))
        return run_as_root_calls

    @_subvol_mock_lexists_is_btrfs_and_run_as_root  # Mocks from _compile()
    def _expected_run_as_root_calls(self, lexists, is_btrfs, run_as_root):
        'Get the commands that each of the *expected* sample items would run'
        lexists.side_effect = _os_path_lexists
        is_btrfs.return_value = True
        subvol = subvol_utils.Subvol(
            f'{TEST_SUBVOLS_DIR}/{FAKE_SUBVOL}',
            already_exists=True,
        )
        phase_item_ids = set()
        for builder_maker, item_ids in si.ORDERED_PHASES:
            phase_item_ids.update(item_ids)
            builder_maker(
                [si.ID_TO_ITEM[i] for i in item_ids],
                LayerOpts(
                    layer_target='fake-target',
                    yum_from_snapshot=self.yum_path,
                )
            )(subvol)

        for item_id, item in si.ID_TO_ITEM.items():
            if item_id not in phase_item_ids:
                item.build(subvol)
        return run_as_root.call_args_list + [
            (
                ([
                    'btrfs', 'property', 'set', '-ts',
                    f'{TEST_SUBVOLS_DIR}/{FAKE_SUBVOL}'.encode(), 'ro', 'true',
                ],),
            ),
            ((_FIND_ARGS,), {'stdout': subprocess.PIPE}),
        ]

    def _assert_equal_call_sets(self, expected, actual):
        '''
        Check that the expected & actual sets of commands are identical.
        Mock `call` objects are unhashable, so we sort.
        '''

        # Compare unittest.mock call lists (which are tuple subclasses) with
        # tuples.  We need to compare `repr` because direct comparisons
        # would end up comparing `str` and `bytes` and fail.
        def tuple_repr(a):
            return repr(tuple(a))

        for e, a in zip(
            sorted(expected, key=tuple_repr),
            sorted(actual, key=tuple_repr),
        ):
            self.assertEqual(e, a)

    def test_compile(self):
        # First, test compilation with no parent layer.
        expected_calls = self._expected_run_as_root_calls()
        self.assertGreater(  # Sanity check: at least one command per item
            len(expected_calls), len(si.ID_TO_ITEM),
        )
        self._assert_equal_call_sets(
            expected_calls, self._compiler_run_as_root_calls(parent_args=[]),
        )

        # Now, add an empty parent layer
        with tempfile.TemporaryDirectory() as parent, \
             mock_subvolume_from_json_file(self, path=parent) as parent_json:
            # Manually add/remove some commands from the "expected" set to
            # accommodate the fact that we have a parent subvolume.
            subvol_path = f'{TEST_SUBVOLS_DIR}/{FAKE_SUBVOL}'.encode()
            # Our unittest.mock.call objects are (args, kwargs) pairs.
            expected_calls_with_parent = [
                c for c in expected_calls if c not in [
                    (
                        (['btrfs', 'subvolume', 'create', subvol_path],),
                        {'_subvol_exists': False},
                    ),
                    ((['chmod', '0755', subvol_path],), {}),
                    ((['chown', 'root:root', subvol_path],), {}),
                ]
            ] + [
                (
                    (['test', '!', '-e', subvol_path],),
                    {'_subvol_exists': False},
                ),
                (
                    ([
                        'btrfs', 'subvolume', 'snapshot',
                        parent.encode(), subvol_path,
                    ],),
                    {'_subvol_exists': False},
                ),
            ]
            self.assertEqual(  # We should've removed 3, and added 2 commands
                len(expected_calls_with_parent) + 1, len(expected_calls),
            )
            self._assert_equal_call_sets(
                expected_calls_with_parent,
                self._compiler_run_as_root_calls(parent_args=[
                    '--parent-layer-json', parent_json,
                ]),
            )


if __name__ == '__main__':
    unittest.main()
