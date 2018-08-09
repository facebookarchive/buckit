#!/usr/bin/env python3
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import unittest.mock

from contextlib import contextmanager
from io import BytesIO

import btrfs_diff.tests.render_subvols as render_sv

from btrfs_diff.subvolume_set import SubvolumeSet
from tests.temp_subvolumes import TempSubvolumes

from ..items import (
    TarballItem, CopyFileItem, MakeDirsItem, ParentLayerItem,
    FilesystemRootItem, gen_parent_layer_items,
)
from ..provides import ProvidesDirectory, ProvidesFile
from ..requires import require_directory

from .mock_subvolume_from_json_file import (
    FAKE_SUBVOLS_DIR, mock_subvolume_from_json_file,
)

DEFAULT_STAT_OPTS = ['--user=root', '--group=root', '--mode=0755']

def _render_subvol(subvol: 'Subvol'):
    subvol_set = SubvolumeSet.new()
    subvolume = render_sv.add_sendstream_to_subvol_set(
        subvol_set, subvol.mark_readonly_and_get_sendstream(),
    )
    subvol.set_readonly(False)
    render_sv.prepare_subvol_set_for_render(subvol_set)
    return render_sv.render_subvolume(subvolume)


class ItemsTestCase(unittest.TestCase):

    def _check_item(self, i, provides, requires, subcommand):
        self.assertEqual(provides, set(i.provides()))
        self.assertEqual(requires, set(i.requires()))
        self.assertEqual(subcommand, i.build_subcommand())

    def test_filesystem_root(self):
        self._check_item(
            FilesystemRootItem(from_target='t'),
            {ProvidesDirectory(path='/')},
            set(),
            [],
        )

    def test_copy_file(self):
        self._check_item(
            CopyFileItem(from_target='t', source='a/b/c', dest='d/'),
            {ProvidesFile(path='d/c')},
            {require_directory('d')},
            ['copy-file', *DEFAULT_STAT_OPTS, 'a/b/c', 'd/c'],
        )
        self._check_item(
            CopyFileItem(from_target='t', source='a/b/c', dest='d'),
            {ProvidesFile(path='d')},
            {require_directory('/')},
            ['copy-file', *DEFAULT_STAT_OPTS, 'a/b/c', 'd'],
        )

    def test_enforce_no_parent_dir(self):
        with self.assertRaisesRegex(AssertionError, r'cannot start with \.\.'):
            CopyFileItem(from_target='t', source='a', dest='a/../../b')

    def test_copy_file_command(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('tar-sv')
            subvol.run_as_root(['mkdir', subvol.path('d')])

            CopyFileItem(
                # `dest` has a rsync-convention trailing /
                from_target='t', source='/dev/null', dest='/d/',
            ).build(subvol)
            self.assertEqual(
                ['(Dir)', {'d': ['(Dir)', {'null': ['(File m755)']}]}],
                _render_subvol(subvol),
            )

            # Fail to write to a nonexistent dir
            with self.assertRaises(subprocess.CalledProcessError):
                CopyFileItem(
                    from_target='t', source='/dev/null', dest='/no_dir/',
                ).build(subvol)

            # Running a second copy to the same destination. This just
            # overwrites the previous file, because we have a build-time
            # check for this, and a run-time check would add overhead.
            CopyFileItem(
                # Test this works without the rsync-covnvention /, too
                from_target='t', source='/dev/null', dest='/d/null',
                # A non-default mode & owner shows that the file was
                # overwritten, and also exercises HasStatOptions.
                mode='u+rw', user='12', group='34',
            ).build(subvol)
            self.assertEqual(
                ['(Dir)', {'d': ['(Dir)', {'null': ['(File m600 o12:34)']}]}],
                _render_subvol(subvol),
            )

    def test_make_dirs(self):
        self._check_item(
            MakeDirsItem(from_target='t', into_dir='x', path_to_make='y/z'),
            {ProvidesDirectory(path='x/y'), ProvidesDirectory(path='x/y/z')},
            {require_directory('x')},
            ['make-dirs', *DEFAULT_STAT_OPTS, '--directory=x', 'y/z'],
        )

    def test_make_dirs_command(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('tar-sv')
            subvol.run_as_root(['mkdir', subvol.path('d')])

            MakeDirsItem(
                from_target='t', path_to_make='/a/b/', into_dir='/d',
                user='77', group='88', mode='u+rx',
            ).build(subvol)
            self.assertEqual(['(Dir)', {
                'd': ['(Dir)', {
                    'a': ['(Dir m500 o77:88)', {
                        'b': ['(Dir m500 o77:88)', {}],
                    }],
                }],
            }], _render_subvol(subvol))

            # The "should never happen" cases -- since we have build-time
            # checks, for simplicity/speed, our runtime clobbers permissions
            # of preexisting directories, and quietly creates non-existent
            # ones with default permissions.
            MakeDirsItem(
                from_target='t', path_to_make='a', into_dir='/no_dir', user='4'
            ).build(subvol)
            MakeDirsItem(
                from_target='t', path_to_make='a/new', into_dir='/d', user='5'
            ).build(subvol)
            self.assertEqual(['(Dir)', {
                'd': ['(Dir)', {
                    # permissions overwritten for this whole tree
                    'a': ['(Dir o5:0)', {
                        'b': ['(Dir o5:0)', {}], 'new': ['(Dir o5:0)', {}],
                    }],
                }],
                'no_dir': ['(Dir)', {  # default permissions!
                    'a': ['(Dir o4:0)', {}],
                }],
            }], _render_subvol(subvol))

    @contextmanager
    def _temp_filesystem(self):
        'Matching Provides are generated by _temp_filesystem_provides'
        with tempfile.TemporaryDirectory() as td_path:

            def p(img_rel_path):
                return os.path.join(td_path, img_rel_path)

            os.makedirs(p('a/b/c'))
            os.makedirs(p('a/d'))

            for filepath in ['a/E', 'a/d/F', 'a/b/c/G']:
                with open(p(filepath), 'w') as f:
                    f.write('Hello, ' + filepath)

            yield td_path

    def _temp_filesystem_provides(self, p=''):
        'Captures what is provided by _temp_filesystem, if installed at `p` '
        'inside the image.'
        return {
            ProvidesDirectory(path=f'{p}/a'),
            ProvidesDirectory(path=f'{p}/a/b'),
            ProvidesDirectory(path=f'{p}/a/b/c'),
            ProvidesDirectory(path=f'{p}/a/d'),
            ProvidesFile(path=f'{p}/a/E'),
            ProvidesFile(path=f'{p}/a/d/F'),
            ProvidesFile(path=f'{p}/a/b/c/G'),
        }

    def test_tarball(self):
        with self._temp_filesystem() as fs_path:
            fs_prefix = fs_path.lstrip('/')

            def strip_fs_prefix(tarinfo):
                if tarinfo.path.startswith(fs_prefix + '/'):
                    tarinfo.path = tarinfo.path[len(fs_prefix) + 1:]
                elif fs_prefix == tarinfo.path:
                    tarinfo.path = '.'
                else:
                    raise AssertionError(
                        f'{tarinfo.path} must start with {fs_prefix}'
                    )
                return tarinfo

            with tempfile.NamedTemporaryFile() as t:
                with tarfile.TarFile(t.name, 'w') as tar_obj:
                    tar_obj.add(fs_path, filter=strip_fs_prefix)

                self._check_item(
                    TarballItem(from_target='t', into_dir='y', tarball=t.name),
                    self._temp_filesystem_provides('y'),
                    {require_directory('y')},
                    ['tar', '--directory=y', t.name],
                )

    def test_tarball_command(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('tar-sv')
            subvol.run_as_root(['mkdir', subvol.path('d')])

            # Fail on pre-existing files
            subvol.run_as_root(['touch', subvol.path('d/exists')])
            with tempfile.NamedTemporaryFile() as t:
                with tarfile.TarFile(t.name, 'w') as tar_obj:
                    tar_obj.addfile(tarfile.TarInfo('exists'))
                with self.assertRaises(subprocess.CalledProcessError):
                    TarballItem(
                        from_target='t', into_dir='/d', tarball=t.name,
                    ).build(subvol)

            # Adding new files & directories works. Overwriting a
            # pre-existing directory leaves the owner+mode of the original
            # directory intact.
            subvol.run_as_root(['mkdir', subvol.path('d/old_dir')])
            subvol.run_as_root(['chown', '123:456', subvol.path('d/old_dir')])
            subvol.run_as_root(['chmod', '0301', subvol.path('d/old_dir')])
            with tempfile.NamedTemporaryFile() as t:
                with tarfile.TarFile(t.name, 'w') as tar_obj:
                    tar_obj.addfile(tarfile.TarInfo('new_file'))

                    new_dir = tarfile.TarInfo('new_dir')
                    new_dir.type = tarfile.DIRTYPE
                    tar_obj.addfile(new_dir)

                    old_dir = tarfile.TarInfo('old_dir')
                    old_dir.type = tarfile.DIRTYPE
                    # These will not be applied because old_dir exists
                    old_dir.uid = 0
                    old_dir.gid = 0
                    old_dir.mode = 0o755
                    tar_obj.addfile(old_dir)

                # Fail when the destination does not exist
                with self.assertRaises(subprocess.CalledProcessError):
                    TarballItem(
                        from_target='t', into_dir='/no_dir', tarball=t.name,
                    ).build(subvol)

                # Check the subvolume content before and after unpacking
                content = ['(Dir)', {'d': ['(Dir)', {
                    'exists': ['(File)'],
                    'old_dir': ['(Dir m301 o123:456)', {}],
                }]}]
                self.assertEqual(content, _render_subvol(subvol))
                TarballItem(
                    from_target='t', into_dir='/d', tarball=t.name,
                ).build(subvol)
                content[1]['d'][1].update({
                    'new_dir': ['(Dir m644)', {}],
                    'new_file': ['(File)'],
                })
                self.assertEqual(content, _render_subvol(subvol))


    def test_parent_layer(self):
        with self._temp_filesystem() as parent_path:
            self._check_item(
                ParentLayerItem(from_target='t', path=parent_path),
                self._temp_filesystem_provides() | {
                    ProvidesDirectory(path='/'),
                },
                set(),
                ['--base-layer-path', parent_path],
            )

    def test_stat_options(self):
        self._check_item(
            MakeDirsItem(
                from_target='t',
                into_dir='x',
                path_to_make='y/z',
                mode=0o733,
                user='cat',
                group='dog',
            ),
            {ProvidesDirectory(path='x/y'), ProvidesDirectory(path='x/y/z')},
            {require_directory('x')},
            [
                'make-dirs',
                '--user=cat', '--group=dog', '--mode=0733',
                '--directory=x', 'y/z',
            ]
        )

    def test_parent_layer_items(self):
        with mock_subvolume_from_json_file(self, path=None):
            self.assertEqual(
                [FilesystemRootItem(from_target='tgt')],
                list(gen_parent_layer_items('tgt', None, FAKE_SUBVOLS_DIR)),
            )

        with mock_subvolume_from_json_file(self, path='potato') as json_file:
            self.assertEqual(
                [ParentLayerItem(from_target='T', path='potato')],
                list(gen_parent_layer_items('T', json_file, FAKE_SUBVOLS_DIR)),
            )


if __name__ == '__main__':
    unittest.main()
