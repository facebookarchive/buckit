#!/usr/bin/env python3
'Helpers for writing tests against btrfs-progs, see e.g. `demo_sendstreams.py`'
import btrfsutil
import contextlib
import os
import subprocess

from typing import List, Union


def subvolume_set_readonly(subvol_path: bytes, *, readonly):
    return btrfsutil.set_subvolume_read_only(subvol_path, readonly)


def mark_subvolume_readonly_and_get_sendstream(
    subvol_path: bytes, *, send_args: List[Union[bytes, str]],
):
    subvolume_set_readonly(subvol_path, readonly=True)

    # Btrfs bug #25329702: in some cases, a `send` without a sync will violate
    # read-after-write consistency and send a "past" view of the filesystem.
    # Do this on the read-only filesystem to improve consistency.
    btrfsutil.sync(subvol_path)

    # Btrfs bug #25379871: our 4.6 kernels have an experimental xattr caching
    # patch, which is broken, and results in xattrs not showing up in the `send`
    # stream unless that metadata is `fsync`ed.  For some dogscience reason,
    # `getfattr` on a file actually triggers such an `fsync`. We do this on a
    # read-only filesystem to improve consistency.
    kernel_ver = subprocess.check_output(['uname', '-r'])
    if kernel_ver.startswith(b'4.6.'):
        subprocess.run([
            'getfattr', '--no-dereference', '--recursive', subvol_path
        ], input=b'', check=True)

    # Shell out since `btrfsutil` has no send/receive support yet
    return subprocess.run(
        ['btrfs', 'send'] + send_args + [subvol_path],
        stdout=subprocess.PIPE, check=True,
    ).stdout


class TempSubvolumes(contextlib.AbstractContextManager):
    'Tracks the subvolumes it creates, and destroys them on context exit.'

    def __init__(self):
        self.paths = []

    def create(self, path: bytes):
        btrfsutil.create_subvolume(path)
        self.paths.append(path)

    def snapshot(self, source: bytes, dest: bytes):
        btrfsutil.create_snapshot(source, dest)
        self.paths.append(dest)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If any of subvolumes are nested, and the parents were made
        # read-only, we won't be able to delete them.
        for path in self.paths:
            subvolume_set_readonly(path, readonly=False)
        for path in reversed(self.paths):
            try:
                btrfsutil.delete_subvolume(path)
            except BaseException:  # Yes, even KeyboardInterrupt & SystemExit
                pass


class CheckedRunTemplate:
    'Shortens repetitive invocations of subprocess.run(..., check=True)'

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __call__(self, *cmd, **kwargs):
        'Accepts and implicitly stringifies float & int arguments.'
        assert all(isinstance(c, (str, bytes, int, float)) for c in cmd)
        subprocess.run(
            [(c if isinstance(c, bytes) else str(c)) for c in cmd],
            **kwargs,
            **self.kwargs,
            check=True,  # Errors must ALWAYS be handled.
        )


def byteme(s: Union[str, bytes]) -> bytes:
    'Byte literals are tiring, just promote strings as needed.'
    return s.encode() if isinstance(s, str) else s


class RelativePath:
    'Callable that converts paths to be relative to a base directory.'

    def __init__(self, *paths_to_join):
        self.base_dir = os.path.join(*(byteme(p) for p in paths_to_join))

    def __call__(self, path: Union[str, bytes]='.'):
        assert not os.path.isabs(path), f'{path} must not be absolute'
        return os.path.normpath(os.path.join(self.base_dir, byteme(path)))
