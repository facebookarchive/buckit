#!/usr/bin/env python3
'''
Inode, and the structures it contains, represent the final, constructed
state of the filesystem. They are immutable, designed to be easy to
construct, and easy to compare in tests.
'''
import stat

from typing import NamedTuple, Optional, Set, Sequence

from .extent import Extent
from .inode_id import InodeID


class InodeOwner(NamedTuple):
    uid: int
    gid: int


class InodeUtimes(NamedTuple):
    ctime: float
    mtime: float
    atime: float


_S_IFMT_TO_FILE_TYPE_NAME = {
    stat.S_IFBLK: 'Block',
    stat.S_IFCHR: 'Char',
    stat.S_IFDIR: 'Dir',
    stat.S_IFIFO: 'FIFO',
    stat.S_IFLNK: 'Symlink',
    stat.S_IFREG: 'File',
    stat.S_IFSOCK: 'Socket',
}

# Future: `frozentype` should let us mirror the `Incomplete*` hierarchy,
# instead of making this enum + union type hack.
class Inode(NamedTuple):
    id: InodeID

    # All inode types
    st_mode: int  # file_type | mode
    owner: InodeOwner
    utimes: InodeUtimes

    # The subsequent fields are specific to particular file_types.  `_new`
    # will assert that they are not None iff they are relevant.

    # FILE
    #
    # The inode's data fork is a concatenation of Chunks, computed from a
    # set of `Extent`s by `extents_to_chunks_with_clones`.
    chunks: Optional[Sequence['Chunk']] = None

    # DEVICE -- block vs character is encoded as `S_IFMT(st_mode)`
    dev: Optional[int] = None

    # SYMLINK
    dest: Optional[bytes] = None

    @staticmethod
    def _new(*, st_mode, chunks=None, dev=None, dest=None, **kwargs):
        assert (stat.S_ISCHR(st_mode) or stat.S_ISBLK(st_mode)) ^ (dev is None)
        assert stat.S_ISREG(st_mode) ^ (chunks is None)
        assert stat.S_ISLNK(st_mode) ^ (dest is None)
        # Symlink permissions are ignored, so ensure they're canonical.
        assert not stat.S_ISLNK(st_mode) or stat.S_IMODE(st_mode) == 0
        return Inode(
            st_mode=st_mode, chunks=chunks, dev=dev, dest=dest, **kwargs,
        )

    def __repr__(self):
        file_type = stat.S_IFMT(self.st_mode)
        name = _S_IFMT_TO_FILE_TYPE_NAME.get(file_type, file_type)
        return f'({name}: {self.id})'


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
