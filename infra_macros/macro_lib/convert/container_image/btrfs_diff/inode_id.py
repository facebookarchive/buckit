#!/usr/bin/env python3
'''
Our inodes' primary purpose is testing. However, writing tests against
arbtirarily selected integer inode IDs is unnecessarily hard.  For this
reason, InodeIDs are tightly integrated with a path mapping, which is used
to represent the Inode instead of the underlying integer ID, whenever
possible.
'''
import itertools
import os

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
            p.decode(errors='surrogateescape') for p in sorted(paths)
        )


def _normpath(p: bytes) -> bytes:
    # Check explicitly since the downstream errors are incomprehensible.
    if not isinstance(p, bytes):
        raise TypeError(f'Expected bytes, got {p}')
    return os.path.normpath(p)


class InodeIDMap:
    '''
    Path -> Inode mapping, represents the directory structure of a filesystem.

    All paths should be relative, making '.' is the root of this map.

    Unlike a real filesystem, this does not:
      - ban hardlinks to directories, or linking a dir inside itself
      - resolve symlinks
    '''
    # Future: the paths are currently marked as `bytes` (and `str` is
    # quietly tolerated for tests), but the actual semantics need to be
    # clarified.  It'll likely be "path relative to EITHER(subvol or vol)".
    id_to_paths: Mapping[int, Set[bytes]]
    path_to_id: Mapping[bytes, InodeID]
    id_to_children: Mapping[int, Set[bytes]]  # dir/path -> dir/path/child

    def __init__(self):
        self.inode_id_counter = itertools.count()
        # We want our own mutable storage so that paths can be added or deleted
        root_id = InodeID(id=next(self.inode_id_counter), id_map=self)
        self.id_to_paths = defaultdict(set, {root_id.id: {b'.'}})
        self.path_to_id = {b'.': root_id}
        self.id_to_children = defaultdict(set)

    def next(self, path: Optional[bytes]=None) -> InodeID:
        inode_id = InodeID(id=next(self.inode_id_counter), id_map=self)
        if path is not None:
            self.add_path(inode_id, path)
        return inode_id

    def _parent_int_id(self, path: bytes) -> Optional[int]:
        # Normalize to map 'a' to '.' and 'b/c' to 'b'.
        parent = os.path.normpath(os.path.dirname(path))
        parent_id = self.path_to_id.get(parent)
        return None if parent_id is None else parent_id.id

    def add_path(self, inode_id: InodeID, path: bytes) -> None:
        path = _normpath(path)
        if os.path.isabs(path):
            raise RuntimeError(f'Need relative path, got {path}')

        parent_int_id = self._parent_int_id(path)
        if parent_int_id is None:
            raise RuntimeError(f'Adding {path}, but parent does not exist')

        old_id = self.path_to_id.setdefault(path, inode_id)
        if old_id != inode_id:
            raise RuntimeError(
                f'Path {path} has 2 inodes: {inode_id.id} and {old_id.id}'
            )

        self.id_to_paths[inode_id.id].add(path)
        self.id_to_children[parent_int_id].add(path)

    def remove_path(self, path: bytes) -> InodeID:
        path = _normpath(path)
        if self.id_to_children.get(self.path_to_id[path].id):
            raise RuntimeError(f'Cannot remove {path} since it has children')

        ino_id = self.path_to_id.pop(path)

        paths = self.id_to_paths[ino_id.id]
        paths.remove(path)
        if not paths:
            del self.id_to_paths[ino_id.id]

        parent_int_id = self._parent_int_id(path)
        children_of_parent = self.id_to_children[parent_int_id]
        children_of_parent.remove(path)
        if not children_of_parent:
            del self.id_to_children[parent_int_id]

        return ino_id

    def get_id(self, path: bytes) -> Optional[InodeID]:
        return self.path_to_id.get(_normpath(path))

    def get_paths(self, inode_id: InodeID) -> Set[bytes]:
        if inode_id.id_map is not self:
            # Avoid InodeID.__repr__ since that would recurse infinitely.
            raise RuntimeError(f'Wrong map for InodeID #{inode_id.id}')
        return self.id_to_paths.get(inode_id.id, set())

    def get_children(self, inode_id: InodeID) -> Set[bytes]:
        return self.id_to_children.get(inode_id.id, set())
