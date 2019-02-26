#!/usr/bin/env python3
import copy
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import unittest.mock

from contextlib import contextmanager, ExitStack

from btrfs_diff.tests.render_subvols import render_sendstream
from tests.temp_subvolumes import TempSubvolumes

from ..items import (
    CopyFileItem, FilesystemRootItem, gen_parent_layer_items, LayerOpts,
    MakeDirsItem, MountItem, ParentLayerItem, PhaseOrder, RemovePathAction,
    RemovePathItem, RpmActionItem, RpmAction, SymlinkToDirItem,
    SymlinkToFileItem, TarballItem, _hash_tarball, _protected_path_set,
    tarball_item_factory,
)
from ..provides import ProvidesDirectory, ProvidesDoNotAccess, ProvidesFile
from ..requires import require_directory, require_file
from ..subvolume_on_disk import SubvolumeOnDisk

from .mock_subvolume_from_json_file import (
    TEST_SUBVOLS_DIR, mock_subvolume_from_json_file,
)

DEFAULT_STAT_OPTS = ['--user=root', '--group=root', '--mode=0755']
DUMMY_LAYER_OPTS = LayerOpts(layer_target='t', yum_from_snapshot='y')


def _render_subvol(subvol: {'Subvol'}):
    rendered = render_sendstream(subvol.mark_readonly_and_get_sendstream())
    subvol.set_readonly(False)  # YES, all our subvolumes are read-write.
    return rendered


def _tarball_item(
    tarball: str, into_dir: str, force_root_ownership: bool = False,
) -> TarballItem:
    'Constructs a common-case TarballItem'
    return tarball_item_factory(
        exit_stack=None,  # unused
        from_target='t',
        into_dir=into_dir,
        tarball=tarball,
        hash='sha256:' + _hash_tarball(tarball, 'sha256'),
        force_root_ownership=force_root_ownership,
    )


def _tarinfo_strip_dir_prefix(dir_prefix):
    'Returns a `filter=` for `TarFile.add`'
    dir_prefix = dir_prefix.lstrip('/')

    def strip_dir_prefix(tarinfo):
        if tarinfo.path.startswith(dir_prefix + '/'):
            tarinfo.path = tarinfo.path[len(dir_prefix) + 1:]
        elif dir_prefix == tarinfo.path:
            tarinfo.path = '.'
        else:
            raise AssertionError(
                f'{tarinfo.path} must start with {dir_prefix}'
            )
        return tarinfo

    return strip_dir_prefix


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
            {ProvidesDirectory(path='/'), ProvidesDoNotAccess(path='/meta')},
            set(),
        )
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.caller_will_create('fs-root')
            FilesystemRootItem.get_phase_builder(
                [FilesystemRootItem(from_target='t')], DUMMY_LAYER_OPTS,
            )(subvol)
            self.assertEqual(
                ['(Dir)', {'meta': ['(Dir)', {}]}], _render_subvol(subvol),
            )

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
        # NB: We don't need to get coverage for this check on ALL the items
        # because the presence of the ProvidesDoNotAccess items it the real
        # safeguard -- e.g. that's what prevents TarballItem from writing
        # to /meta/ or other protected paths.
        with self.assertRaisesRegex(AssertionError, 'cannot start with meta/'):
            CopyFileItem(from_target='t', source='a/b/c', dest='/meta/foo')

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

    def test_mount_item_file_from_host(self):
        mount_config = {
            'is_directory': False,
            'build_source': {'type': 'host', 'source': '/dev/null'},
        }

        def _mount_item(from_target):
            return MountItem(
                from_target=from_target,
                mountpoint='/lala',
                target=None,
                mount_config=mount_config,
            )

        with self.assertRaisesRegex(AssertionError, 'must be located under'):
            _mount_item('t')

        mount_item = _mount_item('//fs_image/features/host_mounts:t')

        bad_mount_config = mount_config.copy()
        bad_mount_config['runtime_source'] = bad_mount_config['build_source']
        with self.assertRaisesRegex(AssertionError, 'Only `build_source` may '):
            MountItem(
                from_target='//fs_image/features/host_mounts:t',
                mountpoint='/lala',
                target=None,
                mount_config=bad_mount_config,
            )

        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            subvol = temp_subvolumes.create('mounter')
            mount_item.build_resolves_targets(
                subvol=subvol,
                target_to_path={},
                subvolumes_dir='unused',
            )

            self.assertEqual(['(Dir)', {
                'lala': ['(File)'],  # An empty mountpoint for /dev/null
                'meta': ['(Dir)', {'private': ['(Dir)', {'mount': ['(Dir)', {
                    'lala': ['(Dir)', {'MOUNT': ['(Dir)', {
                        'is_directory': ['(File d2)'],
                        'build_source': ['(Dir)', {
                            'type': ['(File d5)'],
                            'source': [f'(File d{len("/dev/null") + 1})'],
                        }],
                    }]}],
                }]}]}],
            }], _render_subvol(subvol))
            for filename, contents in (
                ('is_directory', '0\n'),
                ('build_source/type', 'host\n'),
                ('build_source/source', '/dev/null\n'),
            ):
                with open(subvol.path(os.path.join(
                    'meta/private/mount/lala/MOUNT', filename,
                ))) as f:
                    self.assertEqual(contents, f.read())

    def _make_mount_item(self, *, mountpoint, target, mount_config):
        'Ensures that `target` and `mount_config` make the same item.'
        item_from_file = MountItem(
            from_target='t',
            mountpoint=mountpoint,
            target=target,
            mount_config=None,
        )
        self.assertEqual(item_from_file, MountItem(
            from_target='t',
            mountpoint=mountpoint,
            target=None,
            mount_config=mount_config,
        ))
        return item_from_file

    def test_mount_item_default_mountpoint(self):
        with tempfile.TemporaryDirectory() as mnt_target:
            mount_config = {
                'is_directory': True,
                'build_source': {'type': 'layer', 'source': '//fake:path'},
            }
            with open(os.path.join(mnt_target, 'mountconfig.json'), 'w') as f:
                json.dump(mount_config, f)
            # Since our initial mountconfig lacks `default_mountpoint`, the
            # item requires its `mountpoint` to be set.
            with self.assertRaisesRegex(AssertionError, 'lacks mountpoint'):
                MountItem(
                    from_target='t',
                    mountpoint=None,
                    target=mnt_target,
                    mount_config=None,
                )

            # Now, check that the default gets used.
            mount_config['default_mountpoint'] = 'potato'
            with open(os.path.join(mnt_target, 'mountconfig.json'), 'w') as f:
                json.dump(mount_config, f)
            self.assertEqual(self._make_mount_item(
                mountpoint=None,
                target=mnt_target,
                mount_config=mount_config,
            ).mountpoint, 'potato')

    def _check_subvol_mounts_meow(self, subvol):
        self.assertEqual(['(Dir)', {
            'meow': ['(Dir)', {}],
            'meta': ['(Dir)', {'private': ['(Dir)', {'mount': ['(Dir)', {
                'meow': ['(Dir)', {'MOUNT': ['(Dir)', {
                    'is_directory': ['(File d2)'],
                    'build_source': ['(Dir)', {
                        'type': ['(File d6)'],
                        'source': [f'(File d{len("//fake:path") + 1})'],
                    }],
                    'runtime_source': ['(Dir)', {
                        'so': ['(File d3)'],
                        'arbitrary': ['(Dir)', {'j': ['(File d4)']}],
                    }],
                }]}],
            }]}]}],
        }], _render_subvol(subvol))
        for filename, contents in (
            ('is_directory', '1\n'),
            ('build_source/type', 'layer\n'),
            ('build_source/source', '//fake:path\n'),
            ('runtime_source/so', 'me\n'),
            ('runtime_source/arbitrary/j', 'son\n'),
        ):
            with open(subvol.path(os.path.join(
                'meta/private/mount/meow/MOUNT', filename,
            ))) as f:
                self.assertEqual(contents, f.read())

    def _write_layer_json_into(self, subvol, out_dir):
        subvol_path = subvol.path().decode()
        # subvolumes_dir is the grandparent of the subvol by convention
        subvolumes_dir = os.path.dirname(os.path.dirname(subvol_path))
        with open(os.path.join(out_dir, 'layer.json'), 'w') as f:
            SubvolumeOnDisk.from_subvolume_path(
                subvol_path, subvolumes_dir,
            ).to_json_file(f)
        return subvolumes_dir

    def test_mount_item(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes, \
                tempfile.TemporaryDirectory() as source_dir:
            runtime_source = {'so': 'me', 'arbitrary': {'j': 'son'}}
            mount_config = {
                'is_directory': True,
                'build_source': {'type': 'layer', 'source': '//fake:path'},
                'runtime_source': runtime_source,
            }
            with open(os.path.join(source_dir, 'mountconfig.json'), 'w') as f:
                json.dump(mount_config, f)
            self._check_item(
                self._make_mount_item(
                    mountpoint='can/haz',
                    target=source_dir,
                    mount_config=mount_config,
                ),
                {ProvidesDoNotAccess(path='can/haz')},
                {require_directory('can')},
            )

            # Make a subvolume that we will mount inside `mounter`
            mountee = temp_subvolumes.create('moun:tee/volume')
            mountee.run_as_root(['tee', mountee.path('kitteh')], input=b'cheez')

            # These sub-mounts inside `mountee` act as canaries to make sure
            # that (a) `mounter` receives the sub-mounts as a consequence of
            # mounting `mountee` recursively, (b) that unmounting one in
            # `mounter` does not affect the original in `mountee` -- i.e.
            # that rslave propagation is set up correctly, (c) that
            # unmounting in `mountee` immediately affects `mounter`.
            #
            # In practice, our build artifacts should NEVER be mutated after
            # construction (and the only un-mount is implicitly, and
            # seemingly safely, performed by `btrfs subvolume delete`).
            # However, ensuring that we have correct `rslave` propagation is
            # a worthwhile safeguard for host mounts, where an errant
            # `umount` by a user inside their repo could otherwise break
            # their host.
            for submount in ('submount1', 'submount2'):
                mountee.run_as_root(['mkdir', mountee.path(submount)])
                mountee.run_as_root([
                    'mount', '-o', 'bind,ro', source_dir, mountee.path(submount)
                ])
                self.assertTrue(
                    os.path.exists(mountee.path(submount + '/mountconfig.json'))
                )

            # Make the JSON file normally in "buck-out" that refers to `mountee`
            mountee_subvolumes_dir = self._write_layer_json_into(
                mountee, source_dir
            )

            # Mount <mountee> at <mounter>/meow
            mounter = temp_subvolumes.create('moun:ter/volume')
            mount_meow = self._make_mount_item(
                mountpoint='meow',
                target=source_dir,
                mount_config=mount_config,
            )
            self.assertEqual(
                runtime_source, json.loads(mount_meow.runtime_source),
            )
            with self.assertRaisesRegex(AssertionError, ' could not resolve '):
                mount_meow.build_source.to_path(
                    target_to_path={}, subvolumes_dir=mountee_subvolumes_dir,
                )
            mount_meow.build_resolves_targets(
                subvol=mounter,
                target_to_path={'//fake:path': source_dir},
                subvolumes_dir=mountee_subvolumes_dir,
            )

            # This checks the subvolume **contents**, but not the mounts.
            # Ensure the build created a mountpoint, and populated metadata.
            self._check_subvol_mounts_meow(mounter)

            # `mountee` was also mounted at `/meow`
            with open(mounter.path('meow/kitteh')) as f:
                self.assertEqual('cheez', f.read())

            def check_mountee_mounter_submounts(submount_presence):
                for submount, (in_mountee, in_mounter) in submount_presence:
                    self.assertEqual(in_mountee, os.path.exists(
                        mountee.path(submount + '/mountconfig.json')
                    ), f'{submount}, {in_mountee}')
                    self.assertEqual(in_mounter, os.path.exists(
                        mounter.path('meow/' + submount + '/mountconfig.json')
                    ), f'{submount}, {in_mounter}')

            # Both sub-mounts are accessible in both places now.
            check_mountee_mounter_submounts([
                ('submount1', (True, True)),
                ('submount2', (True, True)),
            ])
            # Unmounting `submount1` from `mountee` also affects `mounter`.
            mountee.run_as_root(['umount', mountee.path('submount1')])
            check_mountee_mounter_submounts([
                ('submount1', (False, False)),
                ('submount2', (True, True)),
            ])
            # Unmounting `submount2` from `mounter` doesn't affect `mountee`.
            mounter.run_as_root(['umount', mounter.path('meow/submount2')])
            check_mountee_mounter_submounts([
                ('submount1', (False, False)),
                ('submount2', (True, False)),
            ])

            # Check that we read back the `mounter` metadata, mark `/meow`
            # inaccessible, and do not emit a `ProvidesFile` for `kitteh`.
            pi = ParentLayerItem(from_target='t', path=mounter.path().decode())
            self._check_item(
                pi,
                {
                    ProvidesDirectory(path='/'),
                    ProvidesDoNotAccess(path='/meta'),
                    ProvidesDoNotAccess(path='/meow'),
                },
                set(),
            )
            # Check that we successfully clone mounts from the parent layer.
            mounter_child = temp_subvolumes.caller_will_create('child/volume')
            pi.get_phase_builder([pi], DUMMY_LAYER_OPTS)(mounter_child)

            # The child has the same mount, and the same metadata
            self._check_subvol_mounts_meow(mounter_child)

            # Check that we refuse to create nested mounts.
            nested_mounter = temp_subvolumes.create('nested_mounter')
            nested_item = MountItem(
                from_target='t',
                mountpoint='/whatever',
                target=None,
                mount_config={
                    'is_directory': True,
                    'build_source': {'type': 'layer', 'source': '//:fake'},
                },
            )
            with tempfile.TemporaryDirectory() as d:
                mounter_subvolumes_dir = self._write_layer_json_into(mounter, d)
                with self.assertRaisesRegex(
                    AssertionError, 'Refusing .* nested mount',
                ):
                    nested_item.build_resolves_targets(
                        subvol=nested_mounter,
                        target_to_path={'//:fake': d},
                        subvolumes_dir=mounter_subvolumes_dir,
                    )


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

    def _populate_temp_filesystem(self, img_path):
        'Matching Provides are generated by _temp_filesystem_provides'

        def p(img_rel_path):
            return os.path.join(img_path, img_rel_path)

        os.makedirs(p('a/b/c'))
        os.makedirs(p('a/d'))

        for filepath in ['a/E', 'a/d/F', 'a/b/c/G']:
            with open(p(filepath), 'w') as f:
                f.write('Hello, ' + filepath)

    @contextmanager
    def _temp_filesystem(self):
        with tempfile.TemporaryDirectory() as td_path:
            self._populate_temp_filesystem(td_path)
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
        with self._temp_filesystem() as fs_path, \
                tempfile.TemporaryDirectory() as td:
            tar_path = os.path.join(td, 'test.tar')
            zst_path = os.path.join(td, 'test.tar.zst')

            with tarfile.TarFile(tar_path, 'w') as tar_obj:
                tar_obj.add(fs_path, filter=_tarinfo_strip_dir_prefix(fs_path))
            subprocess.check_call(['zstd', tar_path, '-o', zst_path])

            for path in (tar_path, zst_path):
                self._check_item(
                    _tarball_item(path, 'y'),
                    self._temp_filesystem_provides('y'),
                    {require_directory('y')},
                )

            # Test a hash validation failure, follows the item above
            with self.assertRaisesRegex(AssertionError, 'failed hash vali'):
                TarballItem(
                    from_target='t',
                    into_dir='y',
                    tarball=tar_path,
                    hash='sha256:deadbeef',
                    force_root_ownership=False,
                )

    # NB: We don't need to test `build` because TarballItem has no logic
    # specific to generated vs pre-built tarballs.  It would really be
    # enough just to construct the item, but it was easy to test `provides`.
    def test_tarball_generator(self):
        with self._temp_filesystem() as fs_path, \
                tempfile.NamedTemporaryFile() as t, \
                ExitStack() as exit_stack:
            with tarfile.TarFile(t.name, 'w') as tar_obj:
                tar_obj.add(fs_path, filter=_tarinfo_strip_dir_prefix(fs_path))
            self._check_item(
                tarball_item_factory(
                    exit_stack=exit_stack,
                    from_target='t',
                    into_dir='y',
                    generator='/bin/bash',
                    generator_args=[
                        '-c',
                        'cp "$1" "$2"; basename "$1"',
                        'test_tarball_generator',  # $0
                        t.name,  # $1, making $2 the output directory
                    ],
                    hash='sha256:' + _hash_tarball(t.name, 'sha256'),
                    force_root_ownership=False,
                ),
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
                    _tarball_item(t.name, '/d').build(subvol)

            # Adding new files & directories works. Overwriting a
            # pre-existing directory leaves the owner+mode of the original
            # directory intact.
            subvol.run_as_root(['mkdir', subvol.path('d/old_dir')])
            subvol.run_as_root(['chown', '123:456', subvol.path('d/old_dir')])
            subvol.run_as_root(['chmod', '0301', subvol.path('d/old_dir')])
            subvol_root = temp_subvolumes.snapshot(subvol, 'tar-sv-root')
            subvol_zst = temp_subvolumes.snapshot(subvol, 'tar-sv-zst')
            with tempfile.TemporaryDirectory() as td:
                tar_path = os.path.join(td, 'test.tar')
                zst_path = os.path.join(td, 'test.tar.zst')
                with tarfile.TarFile(tar_path, 'w') as tar_obj:
                    tar_obj.addfile(tarfile.TarInfo('new_file'))

                    new_dir = tarfile.TarInfo('new_dir')
                    new_dir.type = tarfile.DIRTYPE
                    new_dir.uid = 12
                    new_dir.gid = 34
                    tar_obj.addfile(new_dir)

                    old_dir = tarfile.TarInfo('old_dir')
                    old_dir.type = tarfile.DIRTYPE
                    # These will not be applied because old_dir exists
                    old_dir.uid = 0
                    old_dir.gid = 0
                    old_dir.mode = 0o755
                    tar_obj.addfile(old_dir)

                subprocess.check_call(['zstd', tar_path, '-o', zst_path])

                # Fail when the destination does not exist
                with self.assertRaises(subprocess.CalledProcessError):
                    _tarball_item(tar_path, '/no_dir').build(subvol)

                # Before unpacking the tarball
                orig_content = ['(Dir)', {'d': ['(Dir)', {
                    'exists': ['(File)'],
                    'old_dir': ['(Dir m301 o123:456)', {}],
                }]}]
                # After unpacking `tar_path` in `/d`.
                new_content = copy.deepcopy(orig_content)
                new_content[1]['d'][1].update({
                    'new_dir': ['(Dir m644 o12:34)', {}],
                    'new_file': ['(File)'],
                })
                # After unpacking `tar_path` in `/d` with `force_root_ownership`
                new_content_root = copy.deepcopy(new_content)
                # The ownership of 12:34 is gone.
                new_content_root[1]['d'][1]['new_dir'] = ['(Dir m644)', {}]
                self.assertNotEqual(new_content, new_content_root)

                # Check the subvolume content before and after unpacking
                for item, (sv, before, after) in (
                    (
                        _tarball_item(tar_path, '/d/'),
                        (subvol, orig_content, new_content),
                    ),
                    (
                        _tarball_item(tar_path, 'd', force_root_ownership=True),
                        (subvol_root, orig_content, new_content_root),
                    ),
                    (
                        _tarball_item(zst_path, 'd/'),
                        (subvol_zst, orig_content, new_content),
                    ),
                ):
                    self.assertEqual(before, _render_subvol(sv))
                    item.build(sv)
                    self.assertEqual(after, _render_subvol(sv))

    def test_parent_layer_provides(self):
        with TempSubvolumes(sys.argv[0]) as temp_subvolumes:
            parent = temp_subvolumes.create('parent')
            # Permit _populate_temp_filesystem to make writes.
            parent.run_as_root([
                'chown', '--no-dereference', f'{os.geteuid()}:{os.getegid()}',
                parent.path(),
            ])
            self._populate_temp_filesystem(parent.path().decode())
            for create_meta in [False, True]:
                # Check that we properly handle ignoring a /meta if it's present
                if create_meta:
                    parent.run_as_root(['mkdir', parent.path('meta')])
                self._check_item(
                    ParentLayerItem(
                        from_target='t', path=parent.path().decode(),
                    ),
                    self._temp_filesystem_provides() | {
                        ProvidesDirectory(path='/'),
                        ProvidesDoNotAccess(path='/meta'),
                    },
                    set(),
                )

    def test_parent_layer_builder(self):
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
                [ParentLayerItem(from_target='t', path=parent.path().decode())],
                DUMMY_LAYER_OPTS,
            )(child)
            MakeDirsItem(
                from_target='t', into_dir='a', path_to_make='c',
            ).build(child)

            # The parent is unchanged.
            self.assertEqual(parent_content, _render_subvol(parent))
            child_content = copy.deepcopy(parent_content)
            child_content[1]['a'][1]['c'] = ['(Dir)', {}]
            # Since the parent lacked a /meta, the child added it.
            child_content[1]['meta'] = ['(Dir)', {}]
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
                list(gen_parent_layer_items('tgt', None, TEST_SUBVOLS_DIR)),
            )

        with mock_subvolume_from_json_file(self, path='potato') as json_file:
            self.assertEqual(
                [ParentLayerItem(from_target='T', path='potato')],
                list(gen_parent_layer_items('T', json_file, TEST_SUBVOLS_DIR)),
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

            # We refuse to touch protected paths, even with "if_exists".  If
            # the paths started with 'meta', they would trip the check in
            # `_make_path_normal_relative`, so we mock-protect 'xyz'.
            for prot_path in ['xyz', 'xyz/potato/carrot']:
                with unittest.mock.patch(
                    'compiler.items._protected_path_set',
                    side_effect=lambda sv: _protected_path_set(sv) | {'xyz'},
                ), self.assertRaisesRegex(
                    AssertionError, f'Cannot remove protected .*{prot_path}',
                ):
                    RemovePathItem.get_phase_builder([RemovePathItem(
                        from_target='t',
                        action=RemovePathAction.if_exists,
                        path=prot_path,
                    )], DUMMY_LAYER_OPTS)(subvol)

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

            # `yum-from-snapshot` needs a `/meta` directory to work
            subvol.run_as_root(['mkdir', subvol.path('meta')])
            self.assertEqual(
                ['(Dir)', {'meta': ['(Dir)', {}]}], _render_subvol(subvol),
            )

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
            # Maybe fixme: As a result, we end up not asserting ownership /
            # permissions / etc on directories like /var and /dev.
            subvol.run_as_root([
                'rm', '-rf',
                # Annotate all paths since `sudo rm -rf` is scary.
                subvol.path('var/cache/yum'),
                subvol.path('var/lib/rpm'),
                subvol.path('var/lib/yum'),
                subvol.path('var/log/yum.log'),
            ])
            subvol.run_as_root([
                'rmdir',
                subvol.path('dev'),  # made by yum_from_snapshot.py
                subvol.path('meta'),
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
