#!/usr/bin/env python3
import io
import json
import os
import unittest
import unittest.mock

from .. import subvolume_on_disk


_MY_HOST = 'my_host'


class SubvolumeOnDiskTestCase(unittest.TestCase):

    def _test_uuid(self, subvolume_path):
        if self._mock_uuid_stack:
            return self._mock_uuid_stack.pop()
        return f'test_uuid_of:{subvolume_path}'

    def setUp(self):
        'Configure mocks shared by most of the tests.'
        self._mock_uuid_stack = []

        self.patch_btrfs_get_volume_props = unittest.mock.patch.object(
            subvolume_on_disk, '_btrfs_get_volume_props'
        )
        self.mock_btrfs_get_volume_props = \
            self.patch_btrfs_get_volume_props.start()
        self.mock_btrfs_get_volume_props.side_effect = lambda subvolume_path: {
            # Since we key the uuid off the given argument, we don't have to
            # explicitly validate the given path for each mock call.
            'UUID': self._test_uuid(subvolume_path),
        }
        self.addCleanup(self.patch_btrfs_get_volume_props.stop)

        self.patch_getfqdn = unittest.mock.patch('socket.getfqdn')
        self.mock_getfqdn = self.patch_getfqdn.start()
        self.mock_getfqdn.side_effect = lambda: _MY_HOST
        self.addCleanup(self.patch_getfqdn.stop)

    def _check(self, actual_subvol, expected_path, expected_subvol):
        self.assertEqual(expected_path, actual_subvol.subvolume_path())
        self.assertEqual(expected_subvol, actual_subvol)

        # Automatically tests "normal case" serialization & deserialization
        fake_file = io.StringIO()

        # We'll consume UUIDs twice: once for the `to` build-in self-test,
        # once for the `from` validation. So add two of the right UUID.
        stack_size = len(self._mock_uuid_stack)
        self._mock_uuid_stack.extend([actual_subvol.btrfs_uuid] * 2)

        actual_subvol.to_json_file(fake_file)
        fake_file.seek(0)

        self._mock_uuid_stack.append(actual_subvol.btrfs_uuid)
        self.assertEqual(
            actual_subvol,
            subvolume_on_disk.SubvolumeOnDisk.from_json_file(
                fake_file, actual_subvol.subvolumes_dir
            ),
        )

        self.assertEqual(stack_size, len(self._mock_uuid_stack))

    def test_from_json_file_errors(self):
        with self.assertRaisesRegex(RuntimeError, 'Parsing subvolume JSON'):
            subvolume_on_disk.SubvolumeOnDisk.from_json_file(
                io.StringIO('invalid json'), '/subvols'
            )
        with self.assertRaisesRegex(RuntimeError, 'Parsed subvolume JSON'):
            subvolume_on_disk.SubvolumeOnDisk.from_json_file(
                io.StringIO('5'), '/subvols'
            )

    def test_from_serializable_dict_and_validation(self):
        # Note: Unlike test_from_build_buck_plumbing, this test uses a
        # trailing / -- this gets us better coverage.
        subvols = '/test_subvols/'
        good_path = os.path.join(subvols, 'test_name:test_ver')
        good_uuid = self._test_uuid(good_path)
        good = {
            subvolume_on_disk._BTRFS_UUID: good_uuid,
            subvolume_on_disk._HOSTNAME: _MY_HOST,
            subvolume_on_disk._SUBVOLUME_NAME: 'test_name',
            subvolume_on_disk._SUBVOLUME_VERSION: 'test_ver',
        }

        bad_host = good.copy()
        bad_host[subvolume_on_disk._HOSTNAME] = f'NOT_{_MY_HOST}'
        with self.assertRaisesRegex(
            RuntimeError, 'did not come from current host'
        ):
            subvolume_on_disk.SubvolumeOnDisk.from_serializable_dict(
                bad_host, subvols
            )

        bad_uuid = good.copy()
        bad_uuid[subvolume_on_disk._BTRFS_UUID] = 'BAD_UUID'
        with self.assertRaisesRegex(
            RuntimeError, 'UUID in subvolume JSON .* does not match'
        ):
            subvolume_on_disk.SubvolumeOnDisk.from_serializable_dict(
                bad_uuid, subvols
            )

        # Parsing the `good` dict does not throw, and gets the right result.
        good_subvol = subvolume_on_disk.SubvolumeOnDisk.from_serializable_dict(
            good, subvols
        )
        self._check(
            good_subvol,
            good_path,
            subvolume_on_disk.SubvolumeOnDisk(
                btrfs_uuid=good_uuid,
                hostname=_MY_HOST,
                subvolume_name='test_name',
                subvolume_version='test_ver',
                subvolumes_dir=subvols,
            ),
        )

    def test_from_build_buck_plumbing(self):
        # Note: Unlike test_from_serializable_dict_and_validation, this test
        # does NOT use a trailing / -- this gets us better coverage.
        subvols = '/test_subvols'
        subvol_path = '/test_subvols/test_name:test_ver'
        plumbing_output = json.dumps({
            'btrfs_uuid': 'test_uuid',
            'hostname': _MY_HOST,
            'subvolume_path': subvol_path,
        }).encode()

        good_args = {
            'plumbing_output': plumbing_output,
            'subvolumes_dir': subvols,
            'subvolume_name': 'test_name',
            'subvolume_version': 'test_ver',
        }
        subvol = subvolume_on_disk.SubvolumeOnDisk.from_build_buck_plumbing(
            **good_args
        )
        self._check(
            subvol,
            subvol_path,
            subvolume_on_disk.SubvolumeOnDisk(
                btrfs_uuid='test_uuid',
                hostname=_MY_HOST,
                subvolume_name='test_name',
                subvolume_version='test_ver',
                subvolumes_dir=subvols,
            ),
        )

        bad_subvols = good_args.copy()
        bad_subvols['subvolumes_dir'] = '/bad_subvols/'
        bad_name = good_args.copy()
        bad_name['subvolume_name'] = 'bad_name'
        bad_ver = good_args.copy()
        bad_ver['subvolume_version'] = 'bad_ver'

        for bad_args in [bad_subvols, bad_name, bad_ver]:
            with self.assertRaisesRegex(
                RuntimeError, 'unexpected subvolume_path'
            ):
                subvolume_on_disk.SubvolumeOnDisk.from_build_buck_plumbing(
                    **bad_args
                )


class BtrfsVolumePropsTestCase(unittest.TestCase):
    'Separate from SubvolumeOnDiskTestCase because to avoid its mocks.'

    @unittest.mock.patch('subprocess.check_output')
    def test_btrfs_get_volume_props(self, check_output):
        parent = '/subvols/dir/parent'
        check_output.return_value = b'''\
dir/parent
        Name:                   parent
        UUID:                   f96b940f-10d3-fc4e-8b2d-9362af0ee8df
        Parent UUID:            -
        Received UUID:          -
        Creation time:          2017-12-29 21:55:54 -0800
        Subvolume ID:           277
        Generation:             123
        Gen at creation:        103
        Parent ID:              5
        Top level ID:           5
        Flags:                  readonly
        Snapshot(s):
                                dir/foo
                                dir/bar
'''
        self.assertEquals(
            subvolume_on_disk._btrfs_get_volume_props(parent),
            {
                'Name': 'parent',
                'UUID': 'f96b940f-10d3-fc4e-8b2d-9362af0ee8df',
                'Parent UUID': '-',
                'Received UUID': '-',
                'Creation time': '2017-12-29 21:55:54 -0800',
                'Subvolume ID': '277',
                'Generation': '123',
                'Gen at creation': '103',
                'Parent ID': '5',
                'Top level ID': '5',
                'Flags': 'readonly',
                'Snapshot(s)': ['dir/foo', 'dir/bar'],
            }
        )
        check_output.assert_called_once_with(
            ['sudo', 'btrfs', 'subvolume', 'show', parent]
        )

        # Unlike the parent, this has no snapshots, so the format differs.
        child = '/subvols/dir/child'
        check_output.reset_mock()
        check_output.return_value = b'''\
dir/child
        Name:                   child
        UUID:                   a1a3eb3e-eb89-7743-8335-9cd5219248e7
        Parent UUID:            f96b940f-10d3-fc4e-8b2d-9362af0ee8df
        Received UUID:          -
        Creation time:          2017-12-29 21:56:32 -0800
        Subvolume ID:           278
        Generation:             121
        Gen at creation:        107
        Parent ID:              5
        Top level ID:           5
        Flags:                  -
        Snapshot(s):
'''
        self.assertEquals(
            subvolume_on_disk._btrfs_get_volume_props(child),
            {
                'Name': 'child',
                'UUID': 'a1a3eb3e-eb89-7743-8335-9cd5219248e7',
                'Parent UUID': 'f96b940f-10d3-fc4e-8b2d-9362af0ee8df',
                'Received UUID': '-',
                'Creation time': '2017-12-29 21:56:32 -0800',
                'Subvolume ID': '278',
                'Generation': '121',
                'Gen at creation': '107',
                'Parent ID': '5',
                'Top level ID': '5',
                'Flags': '-',
                'Snapshot(s)': [],
            }
        )
        check_output.assert_called_once_with(
            ['sudo', 'btrfs', 'subvolume', 'show', child]
        )
