#!/usr/bin/env python3
'''
Our inodes' primary purpose is testing. However, writing tests against
arbtirarily selected integer inode IDs is unnecessarily hard.  For this
reason, InodeIDs are tightly integrated with a path mapping, which is used
to represent the Inode instead of the underlying integer ID, whenever
possible.
'''
import itertools

from collections import defaultdict

from typing import Mapping, NamedTuple, Optional, Set


class InodeID(NamedTuple):
    id: int
    id_map: 'InodeIDMap'

    def __repr__(self):
        paths = self.id_map.get_paths(self)
        if not paths:
            return f'ANON_INODE#{self.id}'
        return ','.join(
            # Tolerate string paths for the sake of less ugly tests.
            p if isinstance(p, str) else p.decode(errors='surrogateescape')
                for p in sorted(paths)
        )


class InodeIDMap:
    'Path -> Inode mapping, aka the directory structure of a filesystem'
    # Future: the paths are currently marked as `bytes` (and `str` is
    # quietly tolerated for tests), but the actual semantics need to be
    # clarified.  Maybe I'll end up extending SubvolPath to have 3
    # components like `(parent_of_subvol_in_volume, subvol_dir, rel_path)`,
    # and store those...  or maybe these will just be the 3rd component.
    id_to_paths: Mapping[int, Set[bytes]]
    path_to_id: Mapping[bytes, InodeID]

    def __init__(self):
        self.inode_id_counter = itertools.count()
        # We want our own mutable storage so that paths can be added or deleted
        self.id_to_paths = defaultdict(set)
        self.path_to_id = {}

    def next(self, path: Optional[bytes]=None) -> InodeID:
        inode_id = InodeID(id=next(self.inode_id_counter), id_map=self)
        if path is not None:
            self.add_path(inode_id, path)
        return inode_id

    def add_path(self, inode_id: InodeID, path: bytes) -> None:
        old_id = self.path_to_id.setdefault(path, inode_id)
        if old_id != inode_id:
            raise RuntimeError(
                f'Path {path} has 2 inodes: {inode_id.id} and {old_id.id}'
            )
        self.id_to_paths[inode_id.id].add(path)

    def remove_path(self, path: bytes) -> InodeID:
        ino_id = self.path_to_id.pop(path)
        paths = self.id_to_paths[ino_id.id]
        paths.remove(path)
        if not paths:
            del self.id_to_paths[ino_id.id]
        return ino_id

    def get_paths(self, inode_id: InodeID) -> Set[bytes]:
        if inode_id.id_map is not self:
            # Avoid InodeID.__repr__ since that would recurse infinitely.
            raise RuntimeError(f'Wrong map for InodeID #{inode_id.id}')
        return self.id_to_paths.get(inode_id.id, set())

    def get_id(self, path: bytes) -> Optional[InodeID]:
        return self.path_to_id.get(path)
