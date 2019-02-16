#!/usr/bin/env python3
'''
Implementation details of MountItem

NB: Surprisingly, we don't need any special cleanup for the `mount` operations
    performed by `build` and `clone_mounts` -- it appears that subvolume
    deletion, as performed by `subvolume_garbage_collector.py`, implicitly
    lazy-unmounts any mounts therein.
'''
import os

from typing import Iterator, Mapping, NamedTuple

from subvol_utils import Subvol

from .subvolume_on_disk import SubvolumeOnDisk

META_MOUNTS_DIR = 'meta/private/mount'
MOUNT_MARKER = 'MOUNT'


class BuildSource(NamedTuple):
    type: str
    target: str

    def to_path(
        self, *, target_to_path: Mapping[str, str], subvolumes_dir: str,
    ) -> str:
        out_path = target_to_path.get(self.target)
        if out_path is None:
            raise AssertionError(f'MountItem could not resolve {self.target}')
        if self.type == 'layer':
            with open(os.path.join(out_path, 'layer.json')) as infile:
                return SubvolumeOnDisk.from_json_file(
                    infile, subvolumes_dir,
                ).subvolume_path()
        else:  # pragma: no cover
            raise AssertionError(
                f'Bad mount source "{self.type}" for {self.target}'
            )


# Not covering, since this would require META_MOUNTS_DIR to be unreadable.
def _raise(ex):  # pragma: no cover
    raise ex


def mountpoints_from_subvol_meta(subvol: Subvol) -> Iterator[str]:
    'Returns image-relative paths to mountpoints'
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
            yield os.path.dirname(relpath)


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
        to_sv.run_as_root([
            # This preserves the "ro" state of the source mount.
            'mount', '-o', 'bind', from_sv.path(mp), to_sv.path(mp),
        ])
