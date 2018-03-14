#!/usr/bin/env python3
'''
Inode, and the structures it contains, represent the final, constructed
state of the filesystem. They are immutable, designed to be easy to
construct, and easy to compare in tests.
'''
import itertools

from collections import defaultdict
from typing import Mapping, NamedTuple, Set, Sequence

from .extent import Extent


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


# Future: with `deepfrozen` done, it'd be interesting to see if using a
# "freezabletype" idiom makes the Inode/IncompleteInode split clearer.
class IncompleteInode(NamedTuple):
    id: InodeID  # The final `Inode` object inherits this ID.
    extent: Extent

    def __repr__(self):
        return f'(IncompleteInode: {self.id}/{self.extent.length})'


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

    def next(self, paths: Sequence[bytes]) -> InodeID:
        inode_id = InodeID(id=next(self.inode_id_counter), id_map=self)
        self.add_paths(inode_id, paths)
        return inode_id

    def add_paths(self, inode_id: InodeID, paths: Sequence[bytes]) -> None:
        for path in paths:
            old_id = self.path_to_id.setdefault(path, inode_id)
            if old_id != inode_id:
                raise RuntimeError(
                    f'Path {path} has 2 inodes: {inode_id.id} and {old_id.id}'
                )
        self.id_to_paths[inode_id.id].update(paths)

    def get_paths(self, inode_id: InodeID) -> Set[bytes]:
        if inode_id.id_map is not self:
            # Avoid InodeID.__repr__ since that would recurse infinitely.
            raise RuntimeError(f'Wrong map for InodeID #{inode_id.id}')
        return self.id_to_paths.get(inode_id.id, set())


class Inode(NamedTuple):
    id: InodeID
    # The inode's data fork is a concatenation of Chunks, computed from a
    # set of `Extent`s by `extents_to_chunks_with_clones`.
    chunks: Sequence['Chunk']

    def __repr__(self):
        return f'(Inode: {self.id})'


class Clone(NamedTuple):
    'A reference to a byte interval in an Inode.'
    # We could not use Inode objects here, since it's completely reasonable
    # for inode A to contain a clone from B, while B contains a clone from
    # A.  Objects with direct circular dependencies cannot be constructed,
    # so we need the indirection.
    inode_id: InodeID
    offset: int  # The byte offset into the data fork of the `inode_id` Inode.
    length: int

    def __repr__(self):
        return f'{self.inode_id}:{self.offset}+{self.length}'


class ChunkClone(NamedTuple):
    # Clones are only parts of a chunk. The offset of the clone within this
    # chunk is outside of `Clone` to simplify chunk merging.
    offset: int  # Offset into the `Chunk`
    clone: Clone  # What byte range in which Inode does this clone?

    def __repr__(self):
        return f'{repr(self.clone)}@{self.offset}'


class Chunk(NamedTuple):
    kind: Extent.Kind
    length: int
    chunk_clones: Set[ChunkClone]

    def __repr__(self):
        return f'({self.kind.name}/{self.length}' + (
            (': ' + ', '.join(repr(c) for c in self.chunk_clones))
                if self.chunk_clones else ''
        ) + ')'
