#!/usr/bin/env python3
import subprocess
import sys

from compiler.provides import ProvidesFile
from compiler.requires import require_directory
from find_built_subvol import find_built_subvol
from fs_image.fs_utils import Path
from tests.temp_subvolumes import TempSubvolumes

from ..common import ImageSource
from ..install_file import InstallFileItem

from .common import BaseItemTestCase, DUMMY_LAYER_OPTS, render_subvol


class InstallFileItemTestCase(BaseItemTestCase):

    def test_install_file(self):
        exe_item = InstallFileItem(
            from_target='t', source={'source': 'a/b/c'}, dest='d/c',
            is_executable_=True,
        )
        self.assertEqual(0o555, exe_item.mode)
        self.assertEqual(
            ImageSource(source=b'a/b/c', layer=None, path=None),
            exe_item.source,
        )
        self._check_item(
            exe_item,
            {ProvidesFile(path='d/c')},
            {require_directory('d')},
        )

        # Checks `ImageSource.path`, as well as "is_executable_=False"
        data_item = InstallFileItem(
            from_target='t',
            source={'source': 'a', 'path': '/b/q'},
            dest='d',
            is_executable_=False,
        )
        self.assertEqual(0o444, data_item.mode)
        self.assertEqual(
            ImageSource(source=b'a', layer=None, path=b'b/q'),
            data_item.source,
        )
        self.assertEqual(
            b'a/b/q', data_item.source.full_path(DUMMY_LAYER_OPTS),
        )
        self._check_item(
            data_item,
            {ProvidesFile(path='d')},
            {require_directory('/')},
        )

        # NB: We don't need to get coverage for this check on ALL the items
        # because the presence of the ProvidesDoNotAccess items it the real
        # safeguard -- e.g. that's what prevents TarballItem from writing
        # to /meta/ or other protected paths.
        with self.assertRaisesRegex(AssertionError, 'cannot start with meta/'):
            InstallFileItem(
                from_target='t', source={'source': 'a/b/c'}, dest='/meta/foo',
                is_executable_=False,
            )

    def test_install_file_from_layer(self):
        layer_path = Path(__file__).dirname() / 'test-with-one-local-rpm'
        path_in_layer = b'usr/share/rpm_test/cheese2.txt'
        item = InstallFileItem(
            from_target='t',
            source={'layer': layer_path, 'path': '/' + path_in_layer.decode()},
            dest='cheese2',
            is_executable_=False,
        )
        self.assertEqual(0o444, item.mode)
        self.assertEqual(
            ImageSource(source=None, layer=layer_path, path=path_in_layer),
            item.source,
        )
        self.assertEqual(
            find_built_subvol(layer_path).path(path_in_layer),
            # The dummy object works here because `subvolumes_dir` of `None`
            # runs `artifacts_dir` internally, while our "prod" path uses
            # the already-computed value.
            item.source.full_path(DUMMY_LAYER_OPTS),
        )
        self._check_item(
            item,
            {ProvidesFile(path='cheese2')},
            {require_directory('/')},
        )

    def test_install_file_command(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('tar-sv')
            subvol.run_as_root(['mkdir', subvol.path('d')])

            InstallFileItem(
                from_target='t', source={'source': '/dev/null'}, dest='/d/null',
                is_executable_=False,
            ).build(subvol, DUMMY_LAYER_OPTS)
            self.assertEqual(
                ['(Dir)', {'d': ['(Dir)', {'null': ['(File m444)']}]}],
                render_subvol(subvol),
            )

            # Fail to write to a nonexistent dir
            with self.assertRaises(subprocess.CalledProcessError):
                InstallFileItem(
                    from_target='t', source={'source': '/dev/null'},
                    dest='/no_dir/null', is_executable_=False,
                ).build(subvol, DUMMY_LAYER_OPTS)

            # Running a second copy to the same destination. This just
            # overwrites the previous file, because we have a build-time
            # check for this, and a run-time check would add overhead.
            InstallFileItem(
                from_target='t', source={'source': '/dev/null'}, dest='/d/null',
                # A non-default mode & owner shows that the file was
                # overwritten, and also exercises HasStatOptions.
                mode='u+rw', user_group='12:34', is_executable_=False,
            ).build(subvol, DUMMY_LAYER_OPTS)
            self.assertEqual(
                ['(Dir)', {'d': ['(Dir)', {'null': ['(File m600 o12:34)']}]}],
                render_subvol(subvol),
            )
