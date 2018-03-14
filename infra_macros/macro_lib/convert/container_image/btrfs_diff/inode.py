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
from .inode_id import InodeID


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
