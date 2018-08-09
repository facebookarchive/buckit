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

from .enriched_namedtuple import metaclass_new_enriched_namedtuple
from .provides import ProvidesDirectory, ProvidesFile
from .requires import require_directory
from .subvolume_on_disk import SubvolumeOnDisk

from subvol_utils import Subvol


class ImageItem(type):
    'A metaclass for the types of items that can be installed into images.'
    def __new__(metacls, classname, bases, dct):

        # Future: `deepfrozen` has a less clunky way of doing this
        def customize_fields(kwargs):
            fn = dct.get('customize_fields')
            if fn:
                fn(kwargs)
            return kwargs

        return metaclass_new_enriched_namedtuple(
            __class__,
            ['from_target'],
            metacls, classname, bases, dct,
            customize_fields
        )


def _make_path_normal_relative(orig_d: str) -> str:
    '''
    In image-building, we want relative paths that do not start with `..`,
    so that the effects of ImageItems are confined to their destination
    paths. For convenience, we accept absolute paths, too.
    '''
    # lstrip so we treat absolute paths as image-relative
    d = os.path.normpath(orig_d).lstrip('/')
    if d == '..' or d.startswith('../'):
        raise AssertionError(f'path {orig_d} cannot start with ../')
    return d


def _coerce_path_field_normal_relative(kwargs, field: str):
    d = kwargs.get(field)
    if d is not None:
        kwargs[field] = _make_path_normal_relative(d)


class TarballItem(metaclass=ImageItem):
    fields = ['into_dir', 'tarball']

    def customize_fields(kwargs):
        _coerce_path_field_normal_relative(kwargs, 'into_dir')

    def provides(self):
        import tarfile  # Lazy since only this method needs it.
        with tarfile.open(self.tarball, 'r') as f:
            for item in f:
                path = os.path.join(
                    self.into_dir, _make_path_normal_relative(item.name),
                )
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

    def build(self, subvol: Subvol):
        subvol.run_as_root([
            'tar',
            '-C', subvol.path(self.into_dir),
            '-x',
            # The next option is an extra safeguard that is redundant with
            # the compiler's prevention of `provides` conflicts.  It has two
            # consequences:
            #
            #  (1) If a file already exists, `tar` will fail with an error.
            #      It is **not** an error if a directory already exists --
            #      otherwise, one would never be able to safely untar
            #      something into e.g. `/usr/local/bin`.
            #
            #  (2) Less obviously, the option prevents `tar` from
            #      overwriting the permissions of `directory`, as it
            #      otherwise would.
            #
            #      Thanks to the compiler's conflict detection, this should
            #      not come up, but now you know.  Observe us clobber the
            #      permissions without it:
            #
            #        $ mkdir IN OUT
            #        $ touch IN/file
            #        $ chmod og-rwx IN
            #        $ ls -ld IN OUT
            #        drwx------. 2 lesha users 17 Sep 11 21:50 IN
            #        drwxr-xr-x. 2 lesha users  6 Sep 11 21:50 OUT
            #        $ tar -C IN -czf file.tgz .
            #        $ tar -C OUT -xvf file.tgz
            #        ./
            #        ./file
            #        $ ls -ld IN OUT
            #        drwx------. 2 lesha users 17 Sep 11 21:50 IN
            #        drwx------. 2 lesha users 17 Sep 11 21:50 OUT
            #
            #      Adding `--keep-old-files` preserves the metadata of `OUT`:
            #
            #        $ rm -rf OUT ; mkdir out ; ls -ld OUT
            #        drwxr-xr-x. 2 lesha users 6 Sep 11 21:53 OUT
            #        $ tar -C OUT --keep-old-files -xvf file.tgz
            #        ./
            #        ./file
            #        $ ls -ld IN OUT
            #        drwx------. 2 lesha users 17 Sep 11 21:50 IN
            #        drwxr-xr-x. 2 lesha users 17 Sep 11 21:54 OUT
            '--keep-old-files',
            '-f', self.tarball
        ])


class HasStatOptions:
    '''
    Helper for setting `stat (2)` options on files, directories, etc, which
    we are creating inside the image.  Interfaces with `StatOptions` in the
    image build tool.
    '''
    __slots__ = ()
    # `mode` can be an integer fully specifying the bits, or a symbolic
    # string like `u+rx`.  In the latter case, the changes are applied on
    # top of mode 0.
    #
    # The defaut mode 0755 is good for directories, and OK for files.  I'm
    # not trying adding logic to vary the default here, since this really
    # only comes up in tests, and `image_feature` usage should set this
    # explicitly.
    fields = [('mode', 0o755), ('user', 'root'), ('group', 'root')]

    def _mode_impl(self):
        return (  # The symbolic mode must be applied after 0ing all bits.
            f'{self.mode:04o}' if isinstance(self.mode, int)
                else f'a-rwxXst,{self.mode}'
        )

    def build_subcommand_stat_options(self):
        return [
            f'--user={self.user}',
            f'--group={self.group}',
            f'--mode={self._mode_impl()}',
        ]

    def build_stat_options(self, subvol: Subvol, full_target_path: str):
        # -R is not a problem since it cannot be the case that we are
        # creating a directory that already has something inside it.  On the
        # plus side, it helps with nested directory creation.
        subvol.run_as_root([
            'chmod', '-R', self._mode_impl(),
            full_target_path
        ])
        subvol.run_as_root([
            'chown', '-R', f'{self.user}:{self.group}', full_target_path,
        ])


class CopyFileItem(HasStatOptions, metaclass=ImageItem):
    fields = ['source', 'dest']

    def customize_fields(kwargs):
        # rsync convention for the destination: "ends/in/slash/" means "copy
        # into this directory", "does/not/end/with/slash" means "copy with
        # the specified filename".
        kwargs['dest'] = os.path.join(
            kwargs['dest'], os.path.basename(kwargs['source']),
        ) if kwargs['dest'].endswith('/') else kwargs['dest']
        # Normalize after applying the rsync convention, since this would
        # remove any trailing / in 'dest'.
        _coerce_path_field_normal_relative(kwargs, 'dest')

    def provides(self):
        yield ProvidesFile(path=self.dest)

    def requires(self):
        yield require_directory(os.path.dirname(self.dest))

    def build_subcommand(self):
        return [
            'copy-file',
            *self.build_subcommand_stat_options(),
            self.source,
            self.dest,
        ]

    def build(self, subvol: Subvol):
        dest = subvol.path(self.dest)
        subvol.run_as_root(['cp', self.source, dest])
        self.build_stat_options(subvol, dest)


class MakeDirsItem(HasStatOptions, metaclass=ImageItem):
    fields = ['into_dir', 'path_to_make']

    def customize_fields(kwargs):
        _coerce_path_field_normal_relative(kwargs, 'into_dir')
        _coerce_path_field_normal_relative(kwargs, 'path_to_make')

    def provides(self):
        inner_dir = os.path.join(self.into_dir, self.path_to_make)
        while inner_dir != self.into_dir:
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

    def build(self, subvol: Subvol):
        outer_dir = self.path_to_make.split('/', 1)[0]
        inner_dir = subvol.path(os.path.join(self.into_dir, self.path_to_make))
        subvol.run_as_root(['mkdir', '-p', inner_dir])
        self.build_stat_options(
            subvol, subvol.path(os.path.join(self.into_dir, outer_dir)),
        )


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
