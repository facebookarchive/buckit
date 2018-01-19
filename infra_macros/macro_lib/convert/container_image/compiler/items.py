#!/usr/bin/env python3
'''
The classes produced by ImageItem are the various types of items that can be
installed into an image.  The compiler will verify that the specified items
have all of their requirements satisfied, and will then apply them in
dependency order.

To understand how the methods `provides()` and `requires()` affect
dependency resolution / installation order, start with the docblock at the
top of `provides.py`.
'''
import os

from enriched_namedtuple import metaclass_new_enriched_namedtuple
from provides import ProvidesDirectory, ProvidesFile
from requires import require_directory
from subvolume_on_disk import SubvolumeOnDisk


class ImageItem(type):
    'A metaclass for the types of items that can be installed into images.'
    def __new__(metacls, classname, bases, dct):
        return metaclass_new_enriched_namedtuple(
            __class__,
            ['from_target'],
            metacls, classname, bases, dct
        )


class TarballItem(metaclass=ImageItem):
    fields = ['into_dir', 'tarball']

    def provides(self):
        import tarfile  # Lazy since only this method needs it.
        with tarfile.open(self.tarball, 'r') as f:
            for item in f:
                path = os.path.join(self.into_dir, item.name.lstrip('/'))
                if item.isdir():
                    # We do NOT provide the installation directory, and the
                    # image build script tarball extractor takes pains (e.g.
                    # `tar --no-overwrite-dir`) not to touch the extraction
                    # directory.
                    if os.path.normpath(
                        os.path.relpath(path, self.into_dir)
                    ) != '.':
                        yield ProvidesDirectory(path=path)
                else:
                    yield ProvidesFile(path=path)

    def requires(self):
        yield require_directory(self.into_dir)

    def build_subcommand(self):
        return ['tar', f'--directory={self.into_dir}', self.tarball]


class HasStatOptions:
    '''
    Helper for setting `stat (2)` options on files, directories, etc, which
    we are creating inside the image.  Interfaces with `StatOptions` in the
    image build tool.
    '''
    __slots__ = ()
    fields = [('mode', '0755'), ('user', 'root'), ('group', 'root')]

    def build_subcommand_stat_options(self):
        return [
            f'--user={self.user}',
            f'--group={self.group}',
            f'--mode={self.mode}',
        ]


class CopyFileItem(HasStatOptions, metaclass=ImageItem):
    fields = ['source', 'dest']

    def _dest_dir_and_base(self):
        '''
        rsync convention for the destination: "ends/in/slash/" means "copy
        into this directory", "does/not/end/with/slash" means "copy with the
        specified filename".
        '''
        if self.dest.endswith('/'):
            return self.dest, os.path.basename(self.source)
        return os.path.dirname(self.dest), os.path.basename(self.dest)

    def provides(self):
        yield ProvidesFile(path=os.path.join(*self._dest_dir_and_base()))

    def requires(self):
        yield require_directory(self._dest_dir_and_base()[0])

    def build_subcommand(self):
        return [
            'copy-file',
            *self.build_subcommand_stat_options(),
            self.source,
            self.dest,
        ]


class MakeDirsItem(HasStatOptions, metaclass=ImageItem):
    fields = ['into_dir', 'path_to_make']

    def provides(self):
        outer_dir = os.path.normpath(self.into_dir)
        inner_dir = os.path.normpath(
            os.path.join(outer_dir, self.path_to_make.lstrip('/'))
        )
        while inner_dir != outer_dir:
            yield ProvidesDirectory(path=inner_dir)
            inner_dir = os.path.dirname(inner_dir)

    def requires(self):
        yield require_directory(self.into_dir)

    def build_subcommand(self):
        return [
            'make-dirs',
            *self.build_subcommand_stat_options(),
            f'--directory={self.into_dir}',
            self.path_to_make,
        ]


class ParentLayerItem(metaclass=ImageItem):
    fields = ['path']

    def provides(self):
        provided_root = False
        for dirpath, _, filenames in os.walk(self.path):
            dirpath = os.path.relpath(dirpath, self.path)
            dir = ProvidesDirectory(path=dirpath)
            provided_root = provided_root or dir.path == '/'
            yield dir
            for filename in filenames:
                yield ProvidesFile(path=os.path.join(dirpath, filename))
        assert provided_root, 'parent layer {} lacks /'.format(self.path)

    def requires(self):
        return ()

    def build_subcommand(self):
        # Hack: This isn't a true subcommand, but since we provide / and
        # everything implicitly depends on /, it'll always come first.
        return ['--base-layer-path', self.path]


class FilesystemRootItem(metaclass=ImageItem):
    'A trivial item to endow parent-less layers with / directory.'
    fields = []

    def provides(self):
        yield ProvidesDirectory(path='/')

    def requires(self):
        return ()

    def build_subcommand(self):
        return []


def gen_parent_layer_items(target, parent_layer_filename, subvolumes_dir):
    if not parent_layer_filename:
        yield FilesystemRootItem(from_target=target)  # just provides /
    else:
        with open(parent_layer_filename) as infile:
            yield ParentLayerItem(
                from_target=target,
                path=SubvolumeOnDisk.from_json_file(infile, subvolumes_dir)
                    .subvolume_path(),
            )
