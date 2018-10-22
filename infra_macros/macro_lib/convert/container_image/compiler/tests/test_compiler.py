#!/usr/bin/env python3
import itertools
import os
import tempfile
import unittest
import unittest.mock

import subvol_utils

from ..compiler import parse_args, build_image
from .. import subvolume_on_disk as svod

from . import sample_items as si
from .mock_subvolume_from_json_file import (
    FAKE_SUBVOLS_DIR, mock_subvolume_from_json_file,
)

orig_os_walk = os.walk


def _subvol_mock_is_btrfs_and_run_as_root(fn):
    '''
    The purpose of these mocks is to run the compiler while recording
    what commands we WOULD HAVE run on the subvolume.  This is possible
    because all subvolume mutations are supposed to go through
    `Subvol.run_as_root`.  This lets our tests assert that the
    expected operations would have been executed.
    '''
    fn = unittest.mock.patch.object(subvol_utils, '_path_is_btrfs_subvol')(fn)
    fn = unittest.mock.patch.object(subvol_utils.Subvol, 'run_as_root')(fn)
    return fn


def _os_walk(path, **kwargs):
    '''
    DependencyGraph adds a ParentLayerItem to traverse the subvolume, as
    modified by the phases. This ensures the traversal produces a subvol /
    '''
    if path == os.path.join(FAKE_SUBVOLS_DIR, 'SUBVOL'):
        yield (path, [], [])
    else:
        yield from orig_os_walk(path, **kwargs)


class CompilerTestCase(unittest.TestCase):

    def setUp(self):
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

        # This works @mode/opt since the yum binary is baked into our PAR
        self.yum_path = os.path.join(
            os.path.dirname(__file__), 'yum-from-test-snapshot',
        )

    @unittest.mock.patch('os.walk')
    @_subvol_mock_is_btrfs_and_run_as_root
    @unittest.mock.patch.object(svod, '_btrfs_get_volume_props')
    def _compile(
        self, args, btrfs_get_volume_props, is_btrfs, run_as_root, os_walk,
    ):
        os_walk.side_effect = _os_walk
        # We don't have an actual btrfs subvolume, so make up a UUID.
        btrfs_get_volume_props.return_value = {'UUID': 'fake uuid'}
        # Since we're not making subvolumes, we need this so that
        # `Subvolume(..., already_exists=True)` will work.
        is_btrfs.return_value = True
        return build_image(parse_args([
            '--subvolumes-dir', FAKE_SUBVOLS_DIR,
            '--subvolume-rel-path', 'SUBVOL',
            '--yum-from-repo-snapshot', self.yum_path,
            '--child-layer-target', 'CHILD_TARGET',
            '--child-feature-json',
                si.TARGET_TO_PATH[si.mangle(si.T_COPY_DIRS_TAR)],
        ] + args)), run_as_root.call_args_list

    def test_child_dependency_errors(self):
        with self.assertRaisesRegex(
            RuntimeError, 'Odd-length --child-dependencies '
        ):
            self._compile(['--child-dependencies', 'foo'])

        with self.assertRaisesRegex(
            RuntimeError, 'Not every target matches its output: '
        ):
            self._compile(['--child-dependencies', '//a:b', '/repo/b/a'])

        # Our T_COPY_DIRS_TAR feature does have dependencies
        with self.assertRaisesRegex(
            RuntimeError, f'{si.T_BASE}:[^ ]* not in {{}}',
        ):
            self._compile([])

    def test_subvol_serialization_error(self):
        with unittest.mock.patch('socket.getfqdn') as getfqdn:
            getfqdn.side_effect = Exception('NOPE')
            with self.assertRaisesRegex(RuntimeError, 'Serializing subvolume'):
                self._compile([
                    '--child-dependencies',
                    *itertools.chain.from_iterable(
                        si.TARGET_TO_PATH.items()
                    ),
                ])

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
            svod._HOSTNAME: 'fake host',
            svod._SUBVOLUMES_BASE_DIR: FAKE_SUBVOLS_DIR,
            svod._SUBVOLUME_REL_PATH: 'SUBVOL',
        }), res._replace(**{svod._HOSTNAME: 'fake host'}))
        return run_as_root_calls

    @_subvol_mock_is_btrfs_and_run_as_root  # Mocks from _compile()
    def _expected_run_as_root_calls(self, is_btrfs, run_as_root):
        'Get the commands that each of the *expected* sample items would run'
        is_btrfs.return_value = True
        subvol = subvol_utils.Subvol(
            f'{FAKE_SUBVOLS_DIR}/SUBVOL',
            already_exists=True,
        )
        for item in si.ID_TO_ITEM.values():
            if hasattr(item, 'yum_from_snapshot'):
                # sample_items has `/fake/yum` here, but we need the real one
                item._replace(yum_from_snapshot=self.yum_path).build(subvol)
            else:
                item.build(subvol)
        return run_as_root.call_args_list + [
            (
                ([
                    'btrfs', 'property', 'set', '-ts',
                    b'/fake subvolumes dir/SUBVOL', 'ro', 'true',
                ],),
            ),
        ]

    def _assert_equal_call_sets(self, expected, actual):
        '''
        Check that the expected & actual sets of commands are identical.
        Mock `call` objects are unhashable, so we sort.
        '''
        for e, a in zip(sorted(expected), sorted(actual)):
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
            subvol_path = f'{FAKE_SUBVOLS_DIR}/SUBVOL'.encode()
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
