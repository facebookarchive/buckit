#!/usr/bin/env python3
import os
import subprocess
import tempfile

from typing import Union

# Nibble on unicode strings with the intent of treating them as bytes.
Bytey = Union[str, bytes]


# Bite me, Python3
def byteme(s: Bytey) -> bytes:
    'Byte literals are tiring, just promote strings as needed.'
    return s.encode() if isinstance(s, str) else s


class Subvol:
    '''
    ## What is this for?

    This class is to be a privilege / abstraction boundary that allows
    regular, unprivileged Python code to construct images.  Many btrfs
    ioctls require CAP_SYS_ADMIN (or some kind of analog -- e.g. a
    `libguestfs` VM or a privileged server for performing image operations).
    Furthermore, writes to the image-under-construction may require similar
    sorts of privileges to manipulate the image-under-construction as uid 0.

    One approach would be to eschew privilege boundaries, and to run the
    entire build process as `root`.  However, that would forever confine our
    build tool to be run in VMs and other tightly isolated contexts.  Since
    unprivileged image construction is technically possible, we will instead
    take the approach that -- as much as possible -- the build code runs
    unprivileged, as the repo-owning user, and only manipulates the
    filesystem-under-construction via this one class.

    For now, this means shelling out via `sudo`, but in the future,
    `libguestfs` or a privileged filesystem construction proxy could be
    swapped in with minimal changes to the overall structure.

    ## Usage

    - Think of `Subvol` as a ticket to operate on a btrfs subvolume that
      exists, or is about to be created, at a known path on disk. This
      convention lets us cleanly describe paths on a subvolume that does not
      yet physically exist.

    - Call the functions from the btrfs section to manage the subvolumes.

    - Call `subvol.run_as_root()` to use shell commands to manipulate the
      image under construction.

    - Call `subvol.path('image/relative/path')` to refer to paths inside the
      subvolume e.g. in arguments to the `subvol.run_*` functions.
    '''

    def __init__(self, path: Bytey, already_exists=False):
        '''
        `Subvol` can represent not-yet-created subvolumes.  Unless
        already_exists=True, you must call create() or snapshot() to
        actually make the subvolume.
        '''
        self._path = os.path.abspath(byteme(path))
        self._exists = already_exists
        # Ensure that there's a btrfs subvolume at this path. As per @kdave --
        # https://stackoverflow.com/a/32865333
        if self._exists:
            # You'd think I could just `os.statvfs`, but no, not until Py3.7
            # https://bugs.python.org/issue32143
            fs_type = subprocess.run(
                ['stat', '-f', '--format=%T', self._path],
                stdout=subprocess.PIPE,
            ).stdout.decode().strip()
            ino = os.stat(self._path).st_ino
            if fs_type != 'btrfs' or ino != 256:
                raise AssertionError(
                    f'No btrfs subvol at {self._path} -- fs type {fs_type}, '
                    f'inode {ino}.'
                )

    def path(self, path_in_subvol: Bytey=b'.') -> bytes:
        p = os.path.normpath(byteme(path_in_subvol))  # before testing for '..'
        if p.startswith(b'../') or p == b'..':
            raise AssertionError(f'{path_in_subvol} is outside the subvol')
        # The `btrfs` CLI is not very flexible, so it will try to name a
        # subvol '.' if we do not normalize `/subvol/.`.
        return os.path.normpath(os.path.join(self._path, (
            path_in_subvol.encode() if isinstance(path_in_subvol, str)
                else path_in_subvol
            # Without the lstrip, we would lose the subvolume prefix
            # if the supplied path is absolute.
        ).lstrip(b'/')))

    # `_subvol_exists` is a private kwarg letting us `run_as_root` to create
    # new subvolumes, and not just touch existing ones.
    def run_as_root(self, args, *, _subvol_exists=True, stdout=None, **kwargs):
        if _subvol_exists != self._exists:
            raise AssertionError(
                f'{self.path()} exists is {self._exists}, not {_subvol_exists}'
            )
        # Ban our subcommands from writing to stdout, since many of our
        # tools (e.g. make-demo-sendstream, compiler) write structured
        # data to stdout to be usable in pipelines.
        if stdout is None:
            stdout = 2
        return subprocess.run(
            ['sudo', *args], stdout=stdout, **kwargs, check=True,
        )

    # Future: run_in_image()

    # From here on out, every public method directly maps to the btrfs API.
    # For now, we shell out, but in the future, we may talk to a privileged
    # `btrfsutil` helper, or use `guestfs`.

    def _btrfs_run(self, args, **kwargs):
        return self.run_as_root(['btrfs', *args], **kwargs)

    def create(self):
        self._btrfs_run(
            ['subvolume', 'create', self.path()], _subvol_exists=False,
        )
        self._exists = True

    def snapshot(self, source: 'Subvol'):
        # Since `snapshot` has awkward semantics around the `dest`,
        # `_subvol_exists` won't be enough and we ought to ensure that the
        # path physically does not exist.  This needs to run as root, since
        # `os.path.exists` may not have the right permissions.
        self.run_as_root(
            ['test', '!', '-e', self.path()], _subvol_exists=False
        )
        self._btrfs_run(
            ['subvolume', 'snapshot', source.path(), self.path()],
            _subvol_exists=False,
        )
        self._exists = True

    def delete(self):
        self._btrfs_run(['subvolume', 'delete', self.path()])
        self._exists = False

    def set_readonly(self, readonly: bool):
        self._btrfs_run([
            'property', 'set', '-ts', self.path(), 'ro',
            'true' if readonly else 'false',
        ])

    def sync(self):
        self._btrfs_run(['filesystem', 'sync', self.path()])

    def _mark_readonly_and_send(
        self, *, stdout, no_data: bool=False, parent: 'Subvol'=None,
    ) -> subprocess.CompletedProcess:
        self.set_readonly(True)

        # Btrfs bug #25329702: in some cases, a `send` without a sync will
        # violate read-after-write consistency and send a "past" view of the
        # filesystem.  Do this on the read-only filesystem to improve
        # consistency.
        self.sync()

        # Btrfs bug #25379871: our 4.6 kernels have an experimental xattr
        # caching patch, which is broken, and results in xattrs not showing
        # up in the `send` stream unless that metadata is `fsync`ed.  For
        # some dogscience reason, `getfattr` on a file actually triggers
        # such an `fsync`.  We do this on a read-only filesystem to improve
        # consistency.
        kernel_ver = subprocess.check_output(['uname', '-r'])
        if kernel_ver.startswith(b'4.6.'):  # pragma: no cover
            self.run_as_root([
                'getfattr', '--no-dereference', '--recursive', self.path()
            ])

        return self._btrfs_run([
            'send',
            *(['--no-data'] if no_data else []),
            *(['-p', parent.path()] if parent else []),
            self.path(),
        ], stdout=stdout)

    def mark_readonly_and_get_sendstream(self, **kwargs) -> bytes:
        return self._mark_readonly_and_send(
            stdout=subprocess.PIPE, **kwargs,
        ).stdout

    # Future: write_sendstream_to_file()
