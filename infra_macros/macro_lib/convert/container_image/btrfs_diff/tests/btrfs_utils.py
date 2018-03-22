#!/usr/bin/env python3
'Helpers for writing tests against btrfs-progs, see e.g. `demo_sendstreams.py`'
import contextlib
import os
import subprocess

from typing import List, Union


def mark_subvolume_readonly_and_get_sendstream(
    subvol_path: bytes, *, send_args: List[Union[bytes, str]],
):
    subprocess.run([
        'btrfs', 'property', 'set', '-ts', subvol_path, 'ro', 'true'
    ], check=True)

    # Btrfs bug #25329702: in some cases, a `send` without a sync will violate
    # read-after-write consistency and send a "past" view of the filesystem.
    # Do this on the read-only filesystem to improve consistency.
    subprocess.run(['btrfs', 'filesystem', 'sync', subvol_path], check=True)

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

    return subprocess.run(
        ['btrfs', 'send'] + send_args + [subvol_path],
        stdout=subprocess.PIPE, check=True,
    ).stdout


class TempSubvolumes(contextlib.AbstractContextManager):
    'Tracks the subvolumes it creates, and destroys them on context exit.'

    def __init__(self):
        self.paths = []

    def create(self, path: bytes):
        subprocess.run(['btrfs', 'subvolume', 'create', path], check=True)
        self.paths.append(path)

    def snapshot(self, source: bytes, dest: bytes):
        # Future: `dest` has some funky semantics, review if productionizing.
        subprocess.run(
            ['btrfs', 'subvolume', 'snapshot', source, dest], check=True,
        )
        self.paths.append(dest)

    def __exit__(self, exc_type, exc_val, exc_tb):
        for path in reversed(self.paths):
            try:
                subprocess.run([
                    'btrfs', 'subvolume', 'delete', path
                ], check=True)
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
