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
import json
import os
import subprocess

from typing import Iterable, Mapping, NamedTuple, Optional, Set

from . import mount_item
from . import procfs_serde

from .enriched_namedtuple import (
    metaclass_new_enriched_namedtuple, NonConstructibleField,
)
from .provides import ProvidesDirectory, ProvidesDoNotAccess, ProvidesFile
from .requires import require_directory, require_file
from .subvolume_on_disk import SubvolumeOnDisk

from subvol_utils import Subvol

# This path is off-limits to regular image operations, it exists only to
# record image metadata and configuration.  This is at the root, instead of
# in `etc` because that means that `FilesystemRoot` does not have to provide
# `etc` and determine its permissions.  In other words, a top-level "meta"
# directory makes the compiler less opinionated about other image content.
META_DIR = 'meta'


@enum.unique
class PhaseOrder(enum.Enum):
    '''
    With respect to ordering, there are two types of operations that the
    image compiler performs against images.

    (1) Regular additive operations are naturally ordered with respect to
        one another by filesystem dependencies.  For example: we must create
        /usr/bin **BEFORE** copying `:your-tool` there.

    (2) Everything else, including:
         - RPM installation, which has a complex internal ordering, but
           simply needs needs a definitive placement as a block of `yum`
           operations -- due to `yum`'s complexity & various scripts, it's
           not desirable to treat installs as regular additive operations.
         - Path removals.  It is simplest to perform them in bulk, without
           interleaving with other operations.  Removals have a natural
           ordering with respect to each other -- child before parent, to
           avoid tripping "assert_exists" unnecessarily.

    For the operations in (2), this class sets a justifiable deteriminstic
    ordering for black-box blocks of operations, and assumes that each
    individual block's implementation will order its internals sensibly.

    Phases will be executed in the order listed here.

    The operations in (1) are validated, dependency-sorted, and built after
    all of the phases have built.

    IMPORTANT: A new phase implementation MUST:
      - handle pre-existing protected directories via `_protected_dir_set`
      - emit `ProvidesDoNotAccess` if it provides new protected directories
      - ensure that `_protected_dir_set` in future phases knows how to
        discover these protected directories by inspecting the filesystem.
    See `ParentLayerItem`, `RemovePathsItem`, and `MountItem` for examples.

    Future: the complexity around protected directories is a symptom of a
    lack of a strong runtime abstraction.  Specifically, if
    `Subvol.run_as_root` used mount namespaces and read-only bind mounts to
    enforce protected directories (as is done today in `yum-from-snapshot`),
    then it would not be necessary for the compiler to know about them.
    '''
    # This actually creates the subvolume, so it must preced all others.
    PARENT_LAYER = enum.auto()
    # Precedes REMOVE_PATHS because RPM removes **might** be conditional on
    # the presence or absence of files, and we don't want that extra entropy
    # -- whereas file removes fail or succeed predictably.  Precedes
    # RPM_INSTALL somewhat arbitrarily, since _gen_multi_rpm_actions
    # prevents install-remove conflicts between features.
    RPM_REMOVE = enum.auto()
    RPM_INSTALL = enum.auto()
    # This MUST be a separate phase that comes after all the regular items
    # because the dependency sorter has no provisions for eliminating
    # something that another item `provides()`.
    #
    # By having this phase be last, we also allow removing files added by
    # RPM_INSTALL.  The downside is that this is a footgun.  The upside is
    # that e.g.  cleaning up yum log & caches can be done as an
    # `image_feature` instead of being code.  We might also use this to
    # remove e.g.  unnecessary parts of excessively monolithic RPMs.
    REMOVE_PATHS = enum.auto()


class LayerOpts(NamedTuple):
    layer_target: str
    yum_from_snapshot: str


class ImageItem(type):
    'A metaclass for the types of items that can be installed into images.'
    def __new__(metacls, classname, bases, dct):

        # Future: `deepfrozen` has a less clunky way of doing this
        def customize_fields(kwargs):
            fn = dct.get('customize_fields')
            if fn:
                fn(kwargs)
            return kwargs

        # Some items, like RPM actions, are not sorted by dependencies, but
        # get a fixed installation order.  The absence of a phase means the
        # item is ordered via the topo-sort in `dep_graph.py`.
        class PhaseOrderBase:
            __slots__ = ()

            def phase_order(self):
                return None

        return metaclass_new_enriched_namedtuple(
            __class__,
            ['from_target'],
            metacls, classname, (PhaseOrderBase,) + bases, dct,
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
    # This is a directory reserved for image build metadata, so we prevent
    # regular items from writing to it. `d` is never absolute here.
    # NB: This check is redundant with `ProvidesDoNotAccess(path=META_DIR)`,
    # this is just here as a fail-fast backup.
    if (d + '/').startswith(META_DIR + '/'):
        raise AssertionError(f'path {orig_d} cannot start with {META_DIR}/')
    return d


def _coerce_path_field_normal_relative(kwargs, field: str):
    d = kwargs.get(field)
    if d is not None:
        kwargs[field] = _make_path_normal_relative(d)


def _make_rsync_style_dest_path(dest: str, source: str) -> str:
    '''
    rsync convention for a destination: "ends/in/slash/" means "copy
    into this directory", "does/not/end/with/slash" means "copy with
    the specified filename".
    '''

    # Normalize after applying the rsync convention, since this would
    # remove any trailing / in 'dest'.
    return _make_path_normal_relative(
        os.path.join(dest,
            os.path.basename(source)) if dest.endswith('/') else dest
    )


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
            # Future: Bug: `tar` unfortunately FOLLOWS existing symlinks
            # when unpacking.  This isn't dire because the compiler's
            # conflict prevention SHOULD prevent us from going out of the
            # subvolume since this TarballItem's provides would collide with
            # whatever is already present.  However, it's hard to state that
            # with complete confidence, especially if we start adding
            # support for following directory symlinks.
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
        # `chmod` lacks a --no-dereference flag to protect us from following
        # `full_target_path` if it's a symlink.  As far as I know, this
        # should never occur, so just let the exception fly.
        subvol.run_as_root(['test', '!', '-L', full_target_path])
        # -R is not a problem since it cannot be the case that we are
        # creating a directory that already has something inside it.  On
        # the plus side, it helps with nested directory creation.
        subvol.run_as_root([
            'chmod', '-R', self._mode_impl(),
            full_target_path
        ])
        subvol.run_as_root([
            'chown', '--no-dereference', '-R', f'{self.user}:{self.group}',
            full_target_path,
        ])


class CopyFileItem(HasStatOptions, metaclass=ImageItem):
    fields = ['source', 'dest']

    def customize_fields(kwargs):  # noqa: B902
        kwargs['dest'] = _make_rsync_style_dest_path(
            kwargs['dest'], kwargs['source']
        )

    def provides(self):
        yield ProvidesFile(path=self.dest)

    def requires(self):
        yield require_directory(os.path.dirname(self.dest))

    def build(self, subvol: Subvol):
        dest = subvol.path(self.dest)
        subvol.run_as_root(['cp', self.source, dest])
        self.build_stat_options(subvol, dest)


class SymlinkItem(HasStatOptions):
    fields = ['source', 'dest']

    def _customize_fields_impl(kwargs):  # noqa: B902
        _coerce_path_field_normal_relative(kwargs, 'source')

        kwargs['dest'] = _make_rsync_style_dest_path(
            kwargs['dest'], kwargs['source']
        )

    def build(self, subvol: Subvol):
        dest = subvol.path(self.dest)
        # Source is always absolute inside the image subvolume
        source = os.path.join('/', self.source)
        subvol.run_as_root(
            ['ln', '--symbolic', '--no-dereference', source, dest]
        )


class SymlinkToDirItem(SymlinkItem, metaclass=ImageItem):
    customize_fields = SymlinkItem._customize_fields_impl

    def provides(self):
        yield ProvidesDirectory(path=self.dest)

    def requires(self):
        yield require_directory(self.source)
        yield require_directory(os.path.dirname(self.dest))


class SymlinkToFileItem(SymlinkItem, metaclass=ImageItem):
    customize_fields = SymlinkItem._customize_fields_impl

    def provides(self):
        yield ProvidesFile(path=self.dest)

    def requires(self):
        yield require_file(self.source)
        yield require_directory(os.path.dirname(self.dest))


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


# NB: When we split `items.py`, this can just be merged with `mount_item.py`.
class MountItem(metaclass=ImageItem):
    fields = [
        'mountpoint',
        ('build_source', NonConstructibleField),
        ('runtime_source', NonConstructibleField),
        'source',  # always None, its content moves into NonConstructibleFields
    ]

    def customize_fields(kwargs):  # noqa: B902
        with open(os.path.join(kwargs.pop('source'), 'mountconfig.json')) as f:
            cfg = json.load(f)

        if kwargs.get('mountpoint') is None:  # Missing or None => use default
            kwargs['mountpoint'] = cfg.get('default_mountpoint')
            if kwargs['mountpoint'] is None:
                raise AssertionError(f'MountItem {kwargs} lacks mountpoint')
        cfg.pop('default_mountpoint', None)  # No longer needed
        _coerce_path_field_normal_relative(kwargs, 'mountpoint')

        kwargs['build_source'] = mount_item.BuildSource(
            **cfg.pop('build_source')
        )
        # This is supposed to be the run-time equivalent of `build_source`,
        # but for us it's just an opaque JSON blob that the runtime wants.
        kwargs['runtime_source'] = cfg.pop('runtime_source', None)
        kwargs['source'] = None  # Must be set to appease enriched_namedtuple

    def provides(self):
        # For now, nesting of mounts is not supported, and we certainly
        # cannot allow regular items to write inside a mount.
        yield ProvidesDoNotAccess(path=self.mountpoint)

    def requires(self):
        # We don't require the mountpoint itself since it will be shadowed,
        # so this item just makes it with default permissions.
        yield require_directory(os.path.dirname(self.mountpoint))

    def build_resolves_targets(
        self, *,
        subvol: Subvol,
        target_to_path: Mapping[str, str],
        subvolumes_dir: str,
    ):
        mount_dir = os.path.join(
            mount_item.META_MOUNTS_DIR, self.mountpoint, mount_item.MOUNT_MARKER
        )
        for name, data in (
            # NB: Not exporting self.mountpoint since it's implicit in the path.
            ('build_source', self.build_source._asdict()),
            ('runtime_source', self.runtime_source),
        ):
            procfs_serde.serialize(data, subvol, os.path.join(mount_dir, name))
        subvol.run_as_root(['mkdir', subvol.path(self.mountpoint)])
        subvol.run_as_root([
            'mount', '-o', 'ro,bind',
            self.build_source.to_path(
                target_to_path=target_to_path,
                subvolumes_dir=subvolumes_dir,
            ),
            subvol.path(self.mountpoint),
        ])


def _protected_dir_set(subvol: Optional[Subvol]) -> Set[str]:
    '''
    All directories must be relative to the image root, no leading /.
    `subvol=None` if the subvolume doesn't yet exist (for FilesystemRoot).
    '''
    # In the future, this will also return known mountpoints for the subvol.
    dirs = {META_DIR}
    if subvol is not None:
        for mountpoint in mount_item.mountpoints_from_subvol_meta(subvol):
            dirs.add(mountpoint.lstrip('/'))
    # Never absolute: yum-from-snapshot interprets absolute paths as host paths
    assert not any(d.startswith('/') for d in dirs), dirs
    return dirs


def _path_in_protected_dirs(path: str, protected_dirs: Set[str]) -> bool:
    # NB: The O-complexity could obviously be lots better, if needed.
    for prot_dir in protected_dirs:
        if (path + '/').startswith(prot_dir + '/'):
            return True
    return False


def _ensure_meta_dir_exists(subvol: Subvol):
    subvol.run_as_root([
        'mkdir', '--mode=0755', '--parents', subvol.path(META_DIR),
    ])


class ParentLayerItem(metaclass=ImageItem):
    fields = ['path']

    def phase_order(self):
        return PhaseOrder.PARENT_LAYER

    def provides(self):
        parent_subvol = Subvol(self.path, already_exists=True)

        protected_dirs = _protected_dir_set(parent_subvol)
        for dirpath in protected_dirs:
            yield ProvidesDoNotAccess(path=dirpath)

        provided_root = False
        # We need to traverse the parent image as root, so that we have
        # permission to access everything.
        for type_and_path in parent_subvol.run_as_root([
            # -P is the analog of --no-dereference in GNU tools
            'find', '-P', self.path, '-printf', '%y %p\\0',
        ], stdout=subprocess.PIPE).stdout.split(b'\0'):
            if not type_and_path:  # after the trailing \0
                continue
            filetype, abspath = type_and_path.decode().split(' ', 1)
            relpath = os.path.relpath(abspath, self.path)

            # We already "provided" the parent directory above.  Also hide
            # all its children.
            if _path_in_protected_dirs(relpath, protected_dirs):
                continue

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
            mount_item.clone_mounts(parent_subvol, subvol)
            _ensure_meta_dir_exists(subvol)

        return builder


class FilesystemRootItem(metaclass=ImageItem):
    'A simple item to endow parent-less layers with a standard-permissions /'
    fields = []

    def phase_order(self):
        return PhaseOrder.PARENT_LAYER

    def provides(self):
        yield ProvidesDirectory(path='/')
        for p in _protected_dir_set(subvol=None):
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
            _ensure_meta_dir_exists(subvol)

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


class RemovePathAction(enum.Enum):
    assert_exists = 'assert_exists'
    if_exists = 'if_exists'


class RemovePathItem(metaclass=ImageItem):
    fields = ['path', 'action']

    def customize_fields(kwargs):  # noqa: B902
        _coerce_path_field_normal_relative(kwargs, 'path')
        kwargs['action'] = RemovePathAction(kwargs['action'])

    def phase_order(self):
        return PhaseOrder.REMOVE_PATHS

    def __sort_key(self):
        return (self.path, {action: idx for idx, action in enumerate([
            # We sort in reverse order, so by putting "if" first we allow
            # conflicts between "if_exists" and "assert_exists" items to be
            # resolved naturally.
            RemovePathAction.if_exists,
            RemovePathAction.assert_exists,
        ])}[self.action])

    @classmethod
    def get_phase_builder(
        cls, items: Iterable['RemovePathItem'], layer_opts: LayerOpts,
    ):
        # NB: We want `remove_paths` not to be able to remove additions by
        # regular (non-phase) items in the same layer -- that indicates
        # poorly designed `image.feature`s, which should be refactored.  At
        # present, this is only enforced implicitly, because all removes are
        # done before regular items are even validated or sorted.  Enforcing
        # it explicitly is possible by peeking at `DependencyGraph.items`,
        # but the extra complexity doesn't seem worth the faster failure.

        # NB: We could detect collisions between two `assert_exists` removes
        # early, but again, it doesn't seem worth the complexity.

        def builder(subvol: Subvol):
            protected_dirs = _protected_dir_set(subvol)
            # Reverse-lexicographic order deletes inner paths before
            # deleting the outer paths, thus minimizing conflicts between
            # `remove_paths` items.
            for item in sorted(
                items, reverse=True, key=lambda i: i.__sort_key(),
            ):
                if _path_in_protected_dirs(item.path, protected_dirs):
                    # For META_DIR, this is never reached because of
                    # _make_path_normal_relative's check, but for other
                    # protected directories, this is required.
                    raise AssertionError(
                        f'Cannot remove protected {item}: {protected_dirs}'
                    )
                # This ensures that there are no symlinks in item.path that
                # might take us outside of the subvolume.  Since recursive
                # `rm` does not follow symlinks, it is OK if the inode at
                # `item.path` is a symlink (or one of its sub-paths).
                path = subvol.path(item.path, no_dereference_leaf=True)
                if not os.path.lexists(path):
                    if item.action == RemovePathAction.assert_exists:
                        raise AssertionError(f'Path does not exist: {item}')
                    elif item.action == RemovePathAction.if_exists:
                        continue
                    else:  # pragma: no cover
                        raise AssertionError(f'Unknown {item.action}')
                subvol.run_as_root([
                    'rm', '-r',
                    # This prevents us from making removes outside of the
                    # per-repo loopback, which is an important safeguard.
                    # It does not stop us from reaching into other subvols,
                    # but since those have random IDs in the path, this is
                    # nearly impossible to do by accident.
                    '--one-file-system',
                    path,
                ])
            pass

        return builder


class RpmAction(enum.Enum):
    install = 'install'
    # It would be sensible to have a 'remove' that fails if the package is
    # not already installed, but `yum` doesn't seem to support that, and
    # implementing it manually is a hassle.
    remove_if_exists = 'remove_if_exists'


RPM_ACTION_TYPE_TO_YUM_CMD = {
    # We do NOT want people specifying package versions, releases, or
    # architectures via `image_feature`s.  That would be a sure-fire way to
    # get version conflicts.  For the cases where we need version pinning,
    # we'll add a per-layer "version picker" concept.
    RpmAction.install: 'install-n',
    # The way `yum` works, this is a no-op if the package is missing.
    RpmAction.remove_if_exists: 'remove-n',
}


# These items are part of a phase, so they don't get dependency-sorted, so
# there is no `requires()` or `provides()` or `build()` method.
class RpmActionItem(metaclass=ImageItem):
    fields = ['name', 'action']

    def customize_fields(kwargs):  # noqa: B902
        kwargs['action'] = RpmAction(kwargs['action'])

    def phase_order(self):
        return {
            RpmAction.install: PhaseOrder.RPM_INSTALL,
            RpmAction.remove_if_exists: PhaseOrder.RPM_REMOVE,
        }[self.action]

    @classmethod
    def get_phase_builder(
        cls, items: Iterable['RpmActionItem'], layer_opts: LayerOpts,
    ):
        # Do as much validation as possible outside of the builder to give
        # fast feedback to the user.
        assert layer_opts.yum_from_snapshot is not None, (
            f'`image_layer` {layer_opts.layer_target} must set '
            '`yum_from_repo_snapshot`'
        )

        action_to_rpms = {action: set() for action in RpmAction}
        rpm_to_actions = {}
        for item in items:
            assert isinstance(item, RpmActionItem), item
            action_to_rpms[item.action].add(item.name)
            actions = rpm_to_actions.setdefault(item.name, [])
            actions.append((item.action, item.from_target))
            # Raise when a layer has multiple actions for one RPM -- even
            # when all actions are the same.  This can be relaxed if needed.
            if len(actions) != 1:
                raise RuntimeError(
                    f'RPM action conflict for {item.name}: {actions}'
                )

        def builder(subvol: Subvol):
            for action, rpms in action_to_rpms.items():
                if not rpms:
                    continue
                # Future: `yum-from-snapshot` is actually designed to run
                # unprivileged (but we have no nice abstraction for this).
                subvol.run_as_root([
                    # Since `yum-from-snapshot` variants are generally
                    # Python binaries built from this very repo, in
                    # @mode/dev, we would run a symlink-PAR from the
                    # buck-out tree as `root`.  This would leave behind
                    # root-owned `__pycache__` directories, which would
                    # break Buck's fragile cleanup, and cause us to leak old
                    # build artifacts.  This eventually runs the host out of
                    # disk space.  Un-deletable *.pyc files can also
                    # interfere with e.g.  `test-image-layer`, since that
                    # test relies on there being just one `create_ops`
                    # subvolume in `buck-image-out` with the "received UUID"
                    # that was committed to VCS as part of the test
                    # sendstream.
                    'env', 'PYTHONDONTWRITEBYTECODE=1',
                    layer_opts.yum_from_snapshot,
                    *sum((
                        ['--protected-dir', d]
                            for d in _protected_dir_set(subvol)
                    ), []),
                    '--install-root', subvol.path(), '--',
                    RPM_ACTION_TYPE_TO_YUM_CMD[action],
                    # Sort ensures determinism even if `yum` is order-dependent
                    '--assumeyes', '--', *sorted(rpms),
                ])

        return builder
