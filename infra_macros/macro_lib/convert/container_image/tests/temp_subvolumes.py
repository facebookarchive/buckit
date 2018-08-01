#!/usr/bin/env python3
import contextlib
import os
import tempfile

from artifacts_dir import ensure_per_repo_artifacts_dir_exists
from subvol_utils import byteme, Bytey, Subvol
from volume_for_repo import get_volume_for_current_repo


class TempSubvolumes(contextlib.AbstractContextManager):
    'Tracks the subvolumes it creates, and destroys them on context exit.'

    def __init__(self, path_in_repo):
        self.subvols = []
        self._temp_dir_ctx = tempfile.TemporaryDirectory(
            dir=get_volume_for_current_repo(
                1e8, ensure_per_repo_artifacts_dir_exists(path_in_repo),
            )
        )

    def __enter__(self):
        self._temp_dir = self._temp_dir_ctx.__enter__().encode()
        return self

    def _rel_path(self, rel_path: Bytey):
        '''
        Ensures subvolumes live under our temporary directory, which
        improves safety, since its permissions ought to be u+rwx to avoid
        exposing setuid binaries inside the built subvolumes.
        '''
        rel_path = os.path.relpath(
            os.path.realpath(
                os.path.join(self._temp_dir, byteme(rel_path)),
            ),
            start=os.path.realpath(self._temp_dir),
        )
        if (
            rel_path == b'..' or rel_path.startswith(b'../') or
            os.path.isabs(rel_path)
        ):
            raise AssertionError(
                f'{rel_path} must be a subdirectory of {self._temp_dir}'
            )
        return os.path.join(self._temp_dir, rel_path)

    def create(self, rel_path: Bytey) -> Subvol:
        subvol = Subvol(self._rel_path(rel_path))
        subvol.create()
        self.subvols.append(subvol)
        return subvol

    def snapshot(self, source: Subvol, dest_rel_path: Bytey) -> Subvol:
        dest = Subvol(self._rel_path(dest_rel_path))
        dest.snapshot(source)
        self.subvols.append(dest)
        return dest

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If any of subvolumes are nested, and the parents were made
        # read-only, we won't be able to delete them.
        for subvol in self.subvols:
            subvol.set_readonly(False)
        for subvol in reversed(self.subvols):
            try:
                subvol.delete()
            except BaseException:  # Yes, even KeyboardInterrupt & SystemExit
                pass
        self._temp_dir_ctx.__exit__(exc_type, exc_val, exc_tb)
