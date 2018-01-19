#!/usr/bin/env python3
import os
import tempfile
import unittest.mock

from contextlib import contextmanager

FAKE_SUBVOLS_DIR = 'fake subvolumes dir'


@contextmanager
def mock_subvolume_from_json_file(test_case, path):
    '''
    This is useful for getting `gen_parent_layer_items` to produce a mock
    subvolume_path() without actually having a JSON file on disk.

    A path of `None` means that `from_json_file` is not called.
    '''
    with unittest.mock.patch(
        'subvolume_on_disk.SubvolumeOnDisk.from_json_file'
    ) as from_json_file:
        if not path:
            yield None
            from_json_file.assert_not_called()
            return

        with tempfile.TemporaryDirectory() as tmp:
            parent_layer_file = os.path.join(tmp, 'parent.json')
            with open(parent_layer_file, 'w') as f:
                f.write('surprise!')

            def check_call(infile, subvolumes_dir):
                test_case.assertEqual(parent_layer_file, infile.name)
                test_case.assertEqual(FAKE_SUBVOLS_DIR, subvolumes_dir)

                class FakeSubvol:
                    def subvolume_path(self):
                        return path

                return FakeSubvol()

            from_json_file.side_effect = check_call
            yield parent_layer_file
