#!/usr/bin/env python3
import itertools
import os
import subprocess

from typing import Iterable

from subvol_utils import Subvol

from compiler.provides import (
    ProvidesDirectory, ProvidesDoNotAccess, ProvidesFile,
)
from compiler.subvolume_on_disk import SubvolumeOnDisk

from .common import (
    ensure_meta_dir_exists, ImageItem, is_path_protected, LayerOpts,
    PhaseOrder, protected_path_set,
)
from .mount_utils import clone_mounts


class ParentLayerItem(metaclass=ImageItem):
    fields = ['path']

    def phase_order(self):
        return PhaseOrder.PARENT_LAYER

    def provides(self):
        parent_subvol = Subvol(self.path, already_exists=True)

        protected_paths = protected_path_set(parent_subvol)
        for prot_path in protected_paths:
            yield ProvidesDoNotAccess(path=prot_path)

        provided_root = False
        # We need to traverse the parent image as root, so that we have
        # permission to access everything.
        for type_and_path in parent_subvol.run_as_root([
            # -P is the analog of --no-dereference in GNU tools
            #
            # Filter out the protected paths at traversal time.  If one of
            # the paths has a very large or very slow mount, traversing it
            # would have a devastating effect on build times, so let's avoid
            # looking inside protected paths entirely.  An alternative would
            # be to `send` and to parse the sendstream, but this is ok too.
            'find', '-P', self.path, '(', *itertools.dropwhile(
                lambda x: x == '-o',  # Drop the initial `-o`
                itertools.chain.from_iterable([
                    # `normpath` removes the trailing / for protected dirs
                    '-o', '-path', os.path.join(self.path, os.path.normpath(p))
                ] for p in protected_paths),
            ), ')', '-prune', '-o', '-printf', '%y %p\\0',
        ], stdout=subprocess.PIPE).stdout.split(b'\0'):
            if not type_and_path:  # after the trailing \0
                continue
            filetype, abspath = type_and_path.decode().split(' ', 1)
            relpath = os.path.relpath(abspath, self.path)

            # We already "provided" this path above, and it should have been
            # filtered out by `find`.
            assert not is_path_protected(relpath, protected_paths), relpath

            # Future: This provides all symlinks as files, while we should
            # probably provide symlinks to valid directories inside the
            # image as directories to be consistent with SymlinkToDirItem.
            if filetype in ['b', 'c', 'p', 'f', 'l', 's']:
                yield ProvidesFile(path=relpath)
            elif filetype == 'd':
                yield ProvidesDirectory(path=relpath)
            else:  # pragma: no cover
                raise AssertionError(f'Unknown {filetype} for {abspath}')
            if relpath == '.':
                assert filetype == 'd'
                provided_root = True

        assert provided_root, 'parent layer {} lacks /'.format(self.path)

    def requires(self):
        return ()

    @classmethod
    def get_phase_builder(
        cls, items: Iterable['ParentLayerItem'], layer_opts: LayerOpts,
    ):
        parent, = items
        assert isinstance(parent, ParentLayerItem), parent

        def builder(subvol: Subvol):
            parent_subvol = Subvol(parent.path, already_exists=True)
            subvol.snapshot(parent_subvol)
            # This assumes that the parent has everything mounted already.
            clone_mounts(parent_subvol, subvol)
            ensure_meta_dir_exists(subvol, layer_opts)

        return builder


class FilesystemRootItem(metaclass=ImageItem):
    'A simple item to endow parent-less layers with a standard-permissions /'
    fields = []

    def phase_order(self):
        return PhaseOrder.PARENT_LAYER

    def provides(self):
        yield ProvidesDirectory(path='/')
        for p in protected_path_set(subvol=None):
            yield ProvidesDoNotAccess(path=p)

    def requires(self):
        return ()

    @classmethod
    def get_phase_builder(
        cls, items: Iterable['FilesystemRootItem'], layer_opts: LayerOpts,
    ):
        parent, = items
        assert isinstance(parent, FilesystemRootItem), parent

        def builder(subvol: Subvol):
            subvol.create()
            # Guarantee standard / permissions.  This could be a setting,
            # but in practice, probably any other choice would be wrong.
            subvol.run_as_root(['chmod', '0755', subvol.path()])
            subvol.run_as_root(['chown', 'root:root', subvol.path()])
            ensure_meta_dir_exists(subvol, layer_opts)

        return builder


def gen_parent_layer_items(target, parent_layer_json, subvolumes_dir):
    if not parent_layer_json:
        yield FilesystemRootItem(from_target=target)  # just provides /
    else:
        with open(parent_layer_json) as infile:
            yield ParentLayerItem(
                from_target=target,
                path=SubvolumeOnDisk.from_json_file(infile, subvolumes_dir)
                    .subvolume_path(),
            )
