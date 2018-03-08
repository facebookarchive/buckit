#!/usr/bin/env python3
import os
from typing import NamedTuple, Optional


class SubvolPath(NamedTuple):
    subvol: bytes
    path: Optional[bytes] = None  # Only None for e.g. `subvol` and `snapshot`

    def __repr__(self):
        return 'SubvolPath._new(' + repr(
            os.path.join(self.subvol, self.path) if self.path else self.subvol
        ) + ')'

    def __bytes__(self):
        return self.subvol if self.path is None else os.path.join(
            self.subvol, self.path
        )

    @classmethod
    def _new(cls, path: bytes) -> 'SubvolPath':
        # `normpath` is needed since `btrfs receive --dump` is inconsistent
        # about trailing slashes on directory paths.
        return cls(*os.path.normpath(path).split(b'/', 1))
