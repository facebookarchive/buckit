#!/usr/bin/env python3
import copy
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import unittest.mock

from contextlib import contextmanager

from btrfs_diff.tests.render_subvols import render_sendstream
from tests.temp_subvolumes import TempSubvolumes

from ..items import (
    CopyFileItem, FilesystemRootItem, gen_parent_layer_items, LayerOpts,
    MakeDirsItem, ParentLayerItem, PhaseOrder, RemovePathAction,
    RemovePathItem, RpmActionItem, RpmAction, SymlinkToDirItem,
    SymlinkToFileItem, TarballItem,
)
from ..provides import ProvidesDirectory, ProvidesFile
from ..requires import require_directory, require_file

from .mock_subvolume_from_json_file import (
    FAKE_SUBVOLS_DIR, mock_subvolume_from_json_file,
)

DEFAULT_STAT_OPTS = ['--user=root', '--group=root', '--mode=0755']
DUMMY_LAYER_OPTS = LayerOpts(layer_target='t', yum_from_snapshot='y')


def _render_subvol(subvol: {'Subvol'}):
    rendered = render_sendstream(subvol.mark_readonly_and_get_sendstream())
    subvol.set_readonly(False)  # YES, all our subvolumes are read-write.
    return rendered


class ItemsTestCase(unittest.TestCase):

    def setUp(self):  # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

    def _check_item(self, i, provides, requires):
        self.assertEqual(provides, set(i.provides()))
        self.assertEqual(requires, set(i.requires()))

    def test_phase_orders(self):
        self.assertIs(
            None,
            CopyFileItem(from_target='t', source='a', dest='b').phase_order(),
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

    def test_filesystem_root(self):
        self._check_item(
            FilesystemRootItem(from_target='t'),
            {ProvidesDirectory(path='/')},
            set(),
        )
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.caller_will_create('fs-root')
            FilesystemRootItem.get_phase_builder(
                [FilesystemRootItem(from_target='t')], DUMMY_LAYER_OPTS,
            )(subvol)
            self.assertEqual(['(Dir)', {}], _render_subvol(subvol))

    def test_copy_file(self):
        self._check_item(
            CopyFileItem(from_target='t', source='a/b/c', dest='d/'),
            {ProvidesFile(path='d/c')},
            {require_directory('d')},
        )
        self._check_item(
            CopyFileItem(from_target='t', source='a/b/c', dest='d'),
            {ProvidesFile(path='d')},
            {require_directory('/')},
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

    def test_symlink(self):
        self._check_item(
            SymlinkToDirItem(from_target='t', source='x', dest='y'),
            {ProvidesDirectory(path='y')},
            {require_directory('/'), require_directory('/x')},
        )

        self._check_item(
            SymlinkToFileItem(
                from_target='t', source='source_file', dest='dest_symlink'
            ),
            {ProvidesFile(path='dest_symlink')},
            {require_directory('/'), require_file('/source_file')},
        )

    def test_symlink_command(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('tar-sv')
            subvol.run_as_root(['mkdir', subvol.path('dir')])

            # We need a source file to validate a SymlinkToFileItem
            CopyFileItem(
                # `dest` has a rsync-convention trailing /
                from_target='t', source='/dev/null', dest='/file',
            ).build(subvol)
            SymlinkToDirItem(
                from_target='t', source='/dir', dest='/dir_symlink'
            ).build(subvol)
            SymlinkToFileItem(
                from_target='t', source='file', dest='/file_symlink'
            ).build(subvol)

            self.assertEqual(['(Dir)', {
                'dir': ['(Dir)', {}],
                'dir_symlink': ['(Symlink /dir)'],
                'file': ['(File m755)'],
                'file_symlink': ['(Symlink /file)'],
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
        # First, get reasonable coverage of enumerating files and
        # directories without a real btrfs subvol.
        with self._temp_filesystem() as parent_path:
            self._check_item(
                ParentLayerItem(from_target='t', path=parent_path),
                self._temp_filesystem_provides() | {
                    ProvidesDirectory(path='/'),
                },
                set(),
            )
        # Now exercise actually making a btrfs snapshot.
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            parent = temp_subvolumes.create('parent')
            MakeDirsItem(
                from_target='t', into_dir='/', path_to_make='a/b',
            ).build(parent)
            parent_content = ['(Dir)', {'a': ['(Dir)', {'b': ['(Dir)', {}]}]}]
            self.assertEqual(parent_content, _render_subvol(parent))

            # Take a snapshot and add one more directory.
            child = temp_subvolumes.caller_will_create('child')
            ParentLayerItem.get_phase_builder(
                [ParentLayerItem(from_target='t', path=parent.path(),)],
                DUMMY_LAYER_OPTS,
            )(child)
            MakeDirsItem(
                from_target='t', into_dir='a', path_to_make='c',
            ).build(child)

            # The parent is unchanged.
            self.assertEqual(parent_content, _render_subvol(parent))
            child_content = copy.deepcopy(parent_content)
            child_content[1]['a'][1]['c'] = ['(Dir)', {}]
            self.assertEqual(child_content, _render_subvol(child))

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

    def test_remove_item(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('remove_action')
            self.assertEqual(['(Dir)', {}], _render_subvol(subvol))

            MakeDirsItem(
                from_target='t', path_to_make='/a/b/c', into_dir='/',
            ).build(subvol)
            for d in ['d', 'e']:
                CopyFileItem(
                    from_target='t', source='/dev/null', dest=f'/a/b/c/{d}',
                ).build(subvol)
            MakeDirsItem(
                from_target='t', path_to_make='/f/g', into_dir='/',
            ).build(subvol)
            # Checks that `rm` won't follow symlinks
            SymlinkToDirItem(
                from_target='t', source='/f', dest='/a/b/f_sym',
            ).build(subvol)
            for d in ['h', 'i']:
                CopyFileItem(
                    from_target='t', source='/dev/null', dest=f'/f/{d}',
                ).build(subvol)
            SymlinkToDirItem(
                from_target='t', source='/f/i', dest='/f/i_sym',
            ).build(subvol)
            intact_subvol = ['(Dir)', {
                'a': ['(Dir)', {
                    'b': ['(Dir)', {
                        'c': ['(Dir)', {
                            'd': ['(File m755)'],
                            'e': ['(File m755)'],
                        }],
                        'f_sym': ['(Symlink /f)'],
                    }],
                }],
                'f': ['(Dir)', {
                    'g': ['(Dir)', {}],
                    'h': ['(File m755)'],
                    'i': ['(File m755)'],
                    'i_sym': ['(Symlink /f/i)'],
                }],
            }]
            self.assertEqual(intact_subvol, _render_subvol(subvol))

            # Check handling of non-existent paths without removing anything
            remove = RemovePathItem(
                from_target='t',
                action=RemovePathAction.if_exists,
                path='/does/not/exist',
            )
            self.assertEqual(PhaseOrder.REMOVE_PATHS, remove.phase_order())
            RemovePathItem.get_phase_builder([remove], DUMMY_LAYER_OPTS)(subvol)
            with self.assertRaisesRegex(AssertionError, 'does not exist'):
                RemovePathItem.get_phase_builder([
                    RemovePathItem(
                        from_target='t',
                        action=RemovePathAction.assert_exists,
                        path='/does/not/exist',
                    ),
                ], DUMMY_LAYER_OPTS)(subvol)
            self.assertEqual(intact_subvol, _render_subvol(subvol))

            # Now remove most of the subvolume.
            RemovePathItem.get_phase_builder([
                # These 3 removes are not covered by a recursive remove.
                # And we leave behind /f/i, which lets us know that neither
                # `f_sym` nor `i_sym` were followed during their deletion.
                RemovePathItem(
                    from_target='t',
                    action=RemovePathAction.assert_exists,
                    path='/f/i_sym',
                ),
                RemovePathItem(
                    from_target='t',
                    action=RemovePathAction.assert_exists,
                    path='/f/h',
                ),
                RemovePathItem(
                    from_target='t',
                    action=RemovePathAction.assert_exists,
                    path='/f/g',
                ),

                # The next 3 items are intentionally sequenced so that if
                # they were applied in the given order, they would fail.
                RemovePathItem(
                    from_target='t',
                    action=RemovePathAction.if_exists,
                    path='/a/b/c/e',
                ),
                RemovePathItem(
                    from_target='t',
                    action=RemovePathAction.assert_exists,
                    # The surrounding items don't delete /a/b/c/d, e.g. so
                    # this recursive remove is still tested.
                    path='/a/b/',
                ),
                RemovePathItem(
                    from_target='t',
                    action=RemovePathAction.assert_exists,
                    path='/a/b/c/e',
                ),
            ], DUMMY_LAYER_OPTS)(subvol)
            self.assertEqual(['(Dir)', {
                'a': ['(Dir)', {}],
                'f': ['(Dir)', {'i': ['(File m755)']}],
            }], _render_subvol(subvol))

    def test_rpm_action_item(self):
        layer_opts = LayerOpts(
            layer_target='fake-target',
            # This works in @mode/opt since this binary is baked into the XAR
            yum_from_snapshot=os.path.join(
                os.path.dirname(__file__), 'yum-from-test-snapshot',
            ),
        )
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('rpm_action')
            self.assertEqual(['(Dir)', {}], _render_subvol(subvol))

            # The empty action is a no-op
            RpmActionItem.get_phase_builder([], layer_opts)(subvol)
            self.assertEqual(['(Dir)', {}], _render_subvol(subvol))

            # Specifying RPM versions is prohibited
            with self.assertRaises(subprocess.CalledProcessError):
                RpmActionItem.get_phase_builder(
                    [RpmActionItem(
                        from_target='m',
                        name='rpm-test-mice-2',
                        action=RpmAction.install,
                    )],
                    layer_opts,
                )(subvol)

            RpmActionItem.get_phase_builder(
                [
                    RpmActionItem(
                        from_target='t', name=n, action=RpmAction.install,
                    ) for n in ['rpm-test-mice', 'rpm-test-carrot']
                ],
                layer_opts,
            )(subvol)
            # Clean up the `yum` & `rpm` litter before checking the packages.
            subvol.run_as_root([
                'rm', '-rf',
                # Annotate all paths since `sudo rm -rf` is scary.
                subvol.path('var/cache/yum'),
                subvol.path('var/lib/yum'),
                subvol.path('var/lib/rpm'),
                subvol.path('var/log/yum.log'),
            ])
            subvol.run_as_root([
                'rmdir',
                subvol.path('var/cache'),
                subvol.path('var/lib'),
                subvol.path('var/log'),
                subvol.path('var'),
            ])
            self.assertEqual(['(Dir)', {
                'usr': ['(Dir)', {
                    'share': ['(Dir)', {
                        'rpm_test': ['(Dir)', {
                            'carrot.txt': ['(File d13)'],
                            'mice.txt': ['(File d11)'],
                        }],
                    }],
                }],
            }], _render_subvol(subvol))

    def test_rpm_action_conflict(self):
        # Test both install-install and install-remove conflicts.
        for rpm_actions in (
            (('cat', RpmAction.install), ('cat', RpmAction.install)),
            (
                ('dog', RpmAction.remove_if_exists),
                ('dog', RpmAction.install),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'RPM action conflict '):
                # Note that we don't need to run the builder to hit the error
                RpmActionItem.get_phase_builder(
                    [
                        RpmActionItem(from_target='t', name=r, action=a)
                            for r, a in rpm_actions
                    ],
                    DUMMY_LAYER_OPTS,
                )


if __name__ == '__main__':
    unittest.main()
