#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest.mock

from contextlib import contextmanager

from find_built_subvol import subvolumes_dir

from ..subvolume_on_disk import SubvolumeOnDisk

# We need the actual subvolume directory for this mock because the
# `MountItem` build process in `test_compiler.py` loads a real subvolume
# through this path (`:hello_world_base`).
TEST_SUBVOLS_DIR = subvolumes_dir()


@contextmanager
def mock_subvolume_from_json_file(test_case, path, basename='fake_parent.json'):
    '''
    This mock only kicks in when `from_json_file` is called on a file with
    a path with the given `basename`.

    This is useful for getting `gen_parent_layer_items` to produce a mock
    subvolume_path() without actually having a JSON file on disk.

    A path of `None` means that `from_json_file` is not called.
    '''
    orig_from_json_file = SubvolumeOnDisk.from_json_file
    with unittest.mock.patch.object(
        SubvolumeOnDisk, 'from_json_file'
    ) as from_json_file:
        if not path:
            yield None
            from_json_file.assert_not_called()
            return

        with tempfile.TemporaryDirectory() as tmp:
            parent_layer_file = os.path.join(tmp, basename)
            with open(parent_layer_file, 'w') as f:
                f.write('surprise!')

            def check_call(infile, subvolumes_dir):
                if os.path.basename(infile.name) != basename:
                    return orig_from_json_file(infile, subvolumes_dir)

                test_case.assertEqual(parent_layer_file, infile.name)
                test_case.assertEqual(TEST_SUBVOLS_DIR, subvolumes_dir)

                class FakeSubvol:
                    def subvolume_path(self):
                        return path

                return FakeSubvol()

            from_json_file.side_effect = check_call
            yield parent_layer_file
