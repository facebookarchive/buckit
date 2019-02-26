#!/usr/bin/env python3
'''
Implementation details of MountItem

NB: Surprisingly, we don't need any special cleanup for the `mount` operations
    performed by `build` and `clone_mounts` -- it appears that subvolume
    deletion, as performed by `subvolume_garbage_collector.py`, implicitly
    lazy-unmounts any mounts therein.
'''
import json
import os

from typing import AnyStr, Iterator, Mapping, NamedTuple

from subvol_utils import Subvol

from .subvolume_on_disk import SubvolumeOnDisk

META_MOUNTS_DIR = 'meta/private/mount'
MOUNT_MARKER = 'MOUNT'


class BuildSource(NamedTuple):
    type: str
    # This is overloaded to mean different things depending on `type`.
    source: str

    def to_path(
        self, *, target_to_path: Mapping[str, str], subvolumes_dir: str,
    ) -> str:
        if self.type == 'layer':
            out_path = target_to_path.get(self.source)
            if out_path is None:
                raise AssertionError(
                    f'MountItem could not resolve {self.source}'
                )
            with open(os.path.join(out_path, 'layer.json')) as infile:
                subvol = Subvol(SubvolumeOnDisk.from_json_file(
                    infile, subvolumes_dir,
                ).subvolume_path(), already_exists=True)
                # If we allowed mounting a layer that has other mounts
                # inside, it would force us to support nested mounts.  We
                # don't want to do this (yet).
                if os.path.exists(subvol.path(META_MOUNTS_DIR)):
                    raise AssertionError(
                        f'Refusing to mount {subvol.path()} since that would '
                        'require the tooling to support nested mounts.'
                    )
            return subvol.path()
        elif self.type == 'host':
            return self.source
        else:  # pragma: no cover
            raise AssertionError(
                f'Bad mount source "{self.type}" for {self.source}'
            )


# Not covering, since this would require META_MOUNTS_DIR to be unreadable.
def _raise(ex):  # pragma: no cover
    raise ex


def mountpoints_from_subvol_meta(subvol: Subvol) -> Iterator[str]:
    '''
    Returns image-relative paths to mountpoints.  Directories get a trailing
    /, while files do not.  See the `_protected_path_set` docblock if this
    convention proves onerous.
    '''
    mounts_path = subvol.path(META_MOUNTS_DIR)
    if not os.path.exists(mounts_path):
        return
    for path, _next_dirs, _files in os.walk(
        # We are not `chroot`ed, so following links could access outside the
        # image; `followlinks=False` is the default -- explicit for safety.
        mounts_path, onerror=_raise, followlinks=False,
    ):
        relpath = os.path.relpath(path, subvol.path(META_MOUNTS_DIR)).decode()
        if os.path.basename(relpath) == MOUNT_MARKER:
            mountpoint = os.path.dirname(relpath)
            assert not mountpoint.endswith('/'), mountpoint
            # It would be more technically correct to use `subvol.path()`
            # here (since that prevents us from following links outside the
            # image), but this is much more legible and probably safe.
            with open(os.path.join(path, b'is_directory')) as f:
                is_directory = json.load(f)
            yield mountpoint + ('/' if is_directory else '')


def ro_rbind_mount(src: AnyStr, subvol: Subvol, dest_in_subvol: AnyStr):
    # Even though `fs_image` currently does not support mount nesting, the
    # mount must be recursive so that host mounts propagate as expected (we
    # don't want to have to know if a source host directory contains
    # sub-mounts).
    subvol.run_as_root([
        'mount', '-o', 'ro,rbind', src, subvol.path(dest_in_subvol),
    ])
    # Performing mount/unmount operations inside the subvol must not be able
    # to affect the host system, so the tree must be marked at least
    # `rslave`.  It would be defensible to use `rprivate`, but IMO this is
    # more surprising than `rslave` in the case of host mounts -- normal
    # filesystem operations on the host are visible to the container, which
    # suggests that mount changes must be, also.
    #
    # IMPORTANT: Even on fairly recent versions of `util-linux`, merging
    # this into the first `mount` invocation above does NOT work.  Just
    # leave this ugly 2-call version as is.
    #
    # NB: We get slave (not private) propagation since `set_up_volume.sh`
    # sets propagation to shared on the parent mount `buck-image-out/volume`.
    subvol.run_as_root(['mount', '--make-rslave', subvol.path(dest_in_subvol)])
    # Future: if we ever choose to support nesting mounts in `image.layer`s,
    # we might need to additionally `--make-rshared` here, so that if this
    # layer gets mounted inside another, its mount events could be
    # propagated further.  This is an unlikely need, however, because layer
    # mounts follow the build DAG, so there SHOULD NOT be any additional
    # mount events inside the "mountee" layer after it gets constructed...
    # and it can only be mounted in another layer once constructed.


def clone_mounts(from_sv: Subvol, to_sv: Subvol):
    '''
    Use this to transfer mountpoints into a parent from a fresh snapshot.
    This assumes the parent subvolume has mounted all of them.

    Future: once I land my mountinfo lib, we should actually confirm that
    the parent's mountpoints are mounted and are read-only.
    '''
    from_mps = set(mountpoints_from_subvol_meta(from_sv))
    to_mps = set(mountpoints_from_subvol_meta(to_sv))
    assert from_mps == to_mps, (from_mps, to_mps)
    for mp in to_mps:
        ro_rbind_mount(from_sv.path(mp), to_sv, mp)
