#!/usr/bin/env python3
import itertools
import tempfile
import unittest
import unittest.mock

from ..compiler import parse_args, build_image
from ..subvolume_on_disk import SubvolumeOnDisk

from . import sample_items as si
from .mock_subvolume_from_json_file import (
    FAKE_SUBVOLS_DIR, mock_subvolume_from_json_file,
)


class CompilerTestCase(unittest.TestCase):

    @unittest.mock.patch.object(SubvolumeOnDisk, 'from_build_buck_plumbing')
    @unittest.mock.patch('subprocess.check_output')
    def _compile(self, args, check_output, from_build_buck_plumbing):
        check_output.side_effect = lambda cmd: cmd
        from_build_buck_plumbing.side_effect = lambda *args: args
        return build_image(parse_args([
            '--image-build-command', 'FAKE_BUILD',
            '--subvolumes-dir', FAKE_SUBVOLS_DIR,
            '--subvolume-name', 'NAME',
            '--subvolume-version', 'VERSION',
            '--child-layer-target', 'CHILD_TARGET',
            '--child-feature-json',
                si.TARGET_TO_FILENAME[si.mangle(si.T_COPY_DIRS_TAR)],
        ] + args))

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

    def _test_compile(self, parent_in_args, parent_out_args):
        res = self._compile([
            *parent_in_args,
            '--child-dependencies',
            *itertools.chain.from_iterable(si.TARGET_TO_FILENAME.items()),
        ])
        # The last 3 arguments to our mock `from_build_buck_plumbing`.
        self.assertEqual((FAKE_SUBVOLS_DIR, 'NAME', 'VERSION'), res[1:])

        # Try to match each of the sample items' subcommands with the last N
        # elements of the compiler's build command.  This check assumes that
        # item commands are not suffixes of each other, which I think is
        # currently true.  This code is big-O inefficient, but no-one cares.
        cmd = res[0]
        expected_subcommands = {
            tuple(item.build_subcommand())
                for name, item in si.ID_TO_ITEM.items()
                    # The matcher below doesn't handle 0-length subcommands
                    if name != '/'
        }
        while expected_subcommands:
            last_subcommand = None
            for subcommand in expected_subcommands:
                if tuple(cmd[-len(subcommand):]) == subcommand:
                    last_subcommand = subcommand
                    break
            self.assertIsNot(
                None, last_subcommand, f'{expected_subcommands} {cmd}'
            )
            expected_subcommands.remove(last_subcommand)
            del cmd[-len(last_subcommand):]

        # After stripping all the items, we should be left with the preamble.
        self.assertEqual([
            'sudo', 'FAKE_BUILD', 'image', 'build',
            '--no-pkg', '--no-export', '--no-clean-built-layer',
            '--print-buck-plumbing',
            '--tmp-volume', FAKE_SUBVOLS_DIR,
            '--name', 'NAME',
            '--version', 'VERSION',
            *parent_out_args,
        ], cmd)

    def test_compile_no_parent(self):
        self._test_compile(parent_in_args=[], parent_out_args=[])

    def test_compile_with_parent(self):
        with tempfile.TemporaryDirectory() as parent:
            with mock_subvolume_from_json_file(self, path=parent) as json:
                self._test_compile(
                    parent_in_args=['--parent-layer-json', json],
                    parent_out_args=['--base-layer-path', parent],
                )


if __name__ == '__main__':
    unittest.main()
