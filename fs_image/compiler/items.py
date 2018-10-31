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
import enum
import os

from typing import NamedTuple, Optional, FrozenSet

from .enriched_namedtuple import (
    metaclass_new_enriched_namedtuple, NonConstructibleField,
)
from .provides import ProvidesDirectory, ProvidesFile
from .requires import require_directory
from .subvolume_on_disk import SubvolumeOnDisk

from subvol_utils import Subvol


@enum.unique
class PhaseOrder(enum.Enum):
    '''
    With respect to ordering, there are two types of operations that the
    image compiler performs against images.

    (1) Most additive operations are naturally ordered with respect to one
        another by filesystem dependencies.  For example: we must create
        /usr/bin **BEFORE** copying `:your-tool` there.

    (2) Everything else, including:
         - Removals, which commute with each other, and can be ordered
           somewhat arbitrarily with regards to everything else if there are
           no add-remove conflicts,
         - RPM installation, which has a complex internal ordering, but
           simply needs needs a definitive placement as a block of `yum`
           operations -- due to `yum`'s complexity & various scripts, it's
           not desirable to treat installs as regular additive operations.

    For the latter types of operations, this class sets a justifiable
    deteriminstic ordering for black-box blocks of operations, and assumes
    that each individual block's implementation will order its internals
    sensibly.

    Phases will be executed in the order listed here.
    '''
    # This actually creates the subvolume, so it must preced all others.
    PARENT_LAYER = enum.auto()
    # Precedes FILE_REMOVE because RPM removes **might** be conditional on
    # the presence or absence of files, and we don't want that extra entropy
    # -- whereas file removes fail or succeed predictably.  Precedes
    # RPM_INSTALL somewhat arbitrarily, since _gen_multi_rpm_actions
    # prevents install-remove conflicts between features.
    RPM_REMOVE = enum.auto()
    RPM_INSTALL = enum.auto()
    # We allow removing files added by RPM_INSTALL. The downside is that
    # this is a footgun.  The upside is that e.g. cleaning up yum log &
    # caches can be done as an `image_feature` instead of being code.
    FILE_REMOVE = enum.auto()


class ImageItem(type):
    'A metaclass for the types of items that can be installed into images.'
    def __new__(metacls, classname, bases, dct):

        # Future: `deepfrozen` has a less clunky way of doing this
        def customize_fields(kwargs):
            fn = dct.get('customize_fields')
            if fn:
                fn(kwargs)
            # A little hacky: a few "items", like RPM installs, aren't
            # sorted by dependencies, but get a fixed installation order.
            if kwargs['phase_order'] is NonConstructibleField:
                kwargs['phase_order'] = None
            return kwargs

        return metaclass_new_enriched_namedtuple(
            __class__,
            ['from_target', ('phase_order', NonConstructibleField)],
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

    def customize_fields(kwargs):  # noqa: B902
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

    def customize_fields(kwargs):  # noqa: B902
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

    def build(self, subvol: Subvol):
        dest = subvol.path(self.dest)
        subvol.run_as_root(['cp', self.source, dest])
        self.build_stat_options(subvol, dest)


class MakeDirsItem(HasStatOptions, metaclass=ImageItem):
    fields = ['into_dir', 'path_to_make']

    def customize_fields(kwargs):  # noqa: B902
        _coerce_path_field_normal_relative(kwargs, 'into_dir')
        _coerce_path_field_normal_relative(kwargs, 'path_to_make')

    def provides(self):
        inner_dir = os.path.join(self.into_dir, self.path_to_make)
        while inner_dir != self.into_dir:
            yield ProvidesDirectory(path=inner_dir)
            inner_dir = os.path.dirname(inner_dir)

    def requires(self):
        yield require_directory(self.into_dir)

    def build(self, subvol: Subvol):
        outer_dir = self.path_to_make.split('/', 1)[0]
        inner_dir = subvol.path(os.path.join(self.into_dir, self.path_to_make))
        subvol.run_as_root(['mkdir', '-p', inner_dir])
        self.build_stat_options(
            subvol, subvol.path(os.path.join(self.into_dir, outer_dir)),
        )


class ParentLayerItem(metaclass=ImageItem):
    fields = ['path']

    def customize_fields(kwargs):  # noqa: B902
        kwargs['phase_order'] = PhaseOrder.PARENT_LAYER

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

    def build(self, subvol: Subvol):
        subvol.snapshot(Subvol(self.path, already_exists=True))


class FilesystemRootItem(metaclass=ImageItem):
    'A simple item to endow parent-less layers with a standard-permissions /'
    fields = []

    def customize_fields(kwargs):  # noqa: B902
        kwargs['phase_order'] = PhaseOrder.PARENT_LAYER

    def provides(self):
        yield ProvidesDirectory(path='/')

    def requires(self):
        return ()

    def build(self, subvol: Subvol):
        subvol.create()
        # Guarantee standard permissions. This could be made configurable,
        # but in practice, probably any other choice would be wrong.
        subvol.run_as_root(['chmod', '0755', subvol.path()])
        subvol.run_as_root(['chown', 'root:root', subvol.path()])


def gen_parent_layer_items(target, parent_layer_path, subvolumes_dir):
    if not parent_layer_path:
        yield FilesystemRootItem(from_target=target)  # just provides /
    else:
        with open(parent_layer_path) as infile:
            yield ParentLayerItem(
                from_target=target,
                path=SubvolumeOnDisk.from_json_file(infile, subvolumes_dir)
                    .subvolume_path(),
            )


class RpmActionType(enum.Enum):
    install = 'install'
    # It would be sensible to have a 'remove' that fails if the package is
    # not already installed, but `yum` doesn't seem to support that, and
    # implementing it manually is a hassle.
    remove_if_exists = 'remove_if_exists'


RPM_ACTION_TYPE_TO_PHASE_ORDER = {
    RpmActionType.install: PhaseOrder.RPM_INSTALL,
    RpmActionType.remove_if_exists: PhaseOrder.RPM_REMOVE,
}


RPM_ACTION_TYPE_TO_YUM_CMD = {
    # We do NOT want people specifying package versions, releases, or
    # architectures via `image_feature`s.  That would be a sure-fire way to
    # get version conflicts.  For the cases where we need version pinning,
    # we'll add a per-layer "version picker" concept.
    RpmActionType.install: 'install-n',
    # The way `yum` works, this is a no-op if the package is missing.
    RpmActionType.remove_if_exists: 'remove-n',
}


# This quacks like an ImageItem, with one exception: it lacks `from_target`.
# We don't have a good story for attributing RPMs to a build target, since
# multiple build targets may request the same RPM (though it could be done).
# Future: consider a refactor to make explicit the bifurcation in image item
# interfaces between "phased" and "dependency-sorted".
class MultiRpmAction(NamedTuple):
    rpms: FrozenSet[str]
    action: RpmActionType
    yum_from_snapshot: Optional[str]  # Can be None if there are no rpms.
    phase_order: PhaseOrder  # Derived from `action`

    @classmethod
    def new(cls, rpms, action, yum_from_snapshot):
        return cls(
            rpms=rpms,
            action=action,
            yum_from_snapshot=yum_from_snapshot,
            phase_order=RPM_ACTION_TYPE_TO_PHASE_ORDER[action],
        )

    def union(self, other):
        self_metadata = self._replace(rpms={'omitted'})
        other_metadata = other._replace(rpms={'omitted'})
        assert self_metadata == other_metadata, (self_metadata, other_metadata)
        return self._replace(rpms=self.rpms | other.rpms)

    def build(self, subvol: Subvol):
        if not self.rpms:
            return
        assert RPM_ACTION_TYPE_TO_PHASE_ORDER[self.action] is self.phase_order
        assert self.yum_from_snapshot is not None, \
            f'{self} -- your `image_layer` must set `yum_from_repo_snapshot`'
        subvol.run_as_root([
            # Since `yum-from-snapshot` variants are generally Python
            # binaries built from this very repo, in @mode/dev, we would run
            # a symlink-PAR from the buck-out tree as `root`.  This would
            # leave behind root-owned `__pycache__` directories, which would
            # break Buck's fragile cleanup, and cause us to leak old build
            # artifacts.  This eventually runs the host out of disk space,
            # and can also interfere with e.g.  `test-image-layer`, since
            # that test relies on there being just one `create_ops`
            # subvolume in `buck-image-out` with the "received UUID" that
            # was committed to VCS as part of the test sendstream.
            'env', 'PYTHONDONTWRITEBYTECODE=1',
            self.yum_from_snapshot, '--install-root', subvol.path(), '--',
            RPM_ACTION_TYPE_TO_YUM_CMD[self.action],
            # Sort in case `yum` behavior depends on order (for determinism).
            '--assumeyes', '--', *sorted(self.rpms),
        ])
