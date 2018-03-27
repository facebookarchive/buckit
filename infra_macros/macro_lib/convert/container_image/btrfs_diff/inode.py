#!/usr/bin/env python3
'''
Inode, and the structures it contains, represent the final, constructed
state of the filesystem. They are immutable, designed to be easy to
construct, and easy to compare in tests.

## Note on `__repr__`

These are used for tests, so they must be compact & reasonably lossless.
Avoid whitespace when possible, since IncompleteInode uses space separators.
'''
import stat

from datetime import datetime
from typing import NamedTuple, Optional, Set, Sequence, Tuple

from .extent import Extent
from .inode_id import InodeID


class InodeOwner(NamedTuple):
    uid: int
    gid: int

    def __repr__(self):
        return f'{self.uid}:{self.gid}'


MSEC_TO_NSEC = 10 ** 6
SEC_TO_NSEC = 1000 * MSEC_TO_NSEC
MIN_TO_SEC = 60
HOUR_TO_SEC = 60 * MIN_TO_SEC
DAY_TO_SEC = 24 * HOUR_TO_SEC


def _time_delta(a: Tuple[int, int], b: Tuple[int, int]) -> Tuple[int, int]:
    'returns (sec, nsec) -- sec may be negative, nsec is always positive'
    sec_diff = a[0] - b[0]
    nsec_diff = a[1] - b[1]
    nsec = nsec_diff % SEC_TO_NSEC
    nsec_excess = nsec_diff - nsec
    assert nsec_excess % SEC_TO_NSEC == 0, f'{a} - {b}'
    return (sec_diff + nsec_excess // SEC_TO_NSEC, nsec)


def _add_nsec_to_repr(prev: str, nsec: int) -> str:
    '''
    Truncate to milliseconds for compactness, our tests should not care.
    We do NOT round up (too much code), so 999999000 renders as 999.
    '''
    return f'{prev}.{nsec // MSEC_TO_NSEC:03}'.rstrip('0').rstrip('.')


def _repr_time_delta(sec: int, nsec: int) -> str:
    'sec may be negative, nsec is always positive'
    if sec < 0:
        sign = '-'
        sec = -sec
        if nsec > 0:
            sec -= 1
            nsec = SEC_TO_NSEC - nsec
    else:
        sign = '+'
    return _add_nsec_to_repr(f'{sign}{sec}', nsec)


def _repr_time(sec: int, nsec: int) -> str:
    sec_str = datetime.utcfromtimestamp(sec).strftime('%y/%m/%d.%H:%M:%S')
    return _add_nsec_to_repr(sec_str, nsec)


class InodeUtimes(NamedTuple):
    ctime: Tuple[int, int]  # sec, nsec
    mtime: Tuple[int, int]
    atime: Tuple[int, int]

    def __repr__(self):
        c_to_m = _repr_time_delta(*_time_delta(self.mtime, self.ctime))
        m_to_a = _repr_time_delta(*_time_delta(self.atime, self.mtime))
        return f'{_repr_time(*self.ctime)}{c_to_m}{m_to_a}'


_S_IFMT_TO_FILE_TYPE_NAME = {
    stat.S_IFBLK: 'Block',
    stat.S_IFCHR: 'Char',
    stat.S_IFDIR: 'Dir',
    stat.S_IFIFO: 'FIFO',
    stat.S_IFLNK: 'Symlink',
    stat.S_IFREG: 'File',
    stat.S_IFSOCK: 'Sock',
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
