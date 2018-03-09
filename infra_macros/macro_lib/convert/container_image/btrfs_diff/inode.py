#!/usr/bin/env python3
'''
The workflow for creating a mock filesystem is as follows:

 - Sequentially apply `btrfs send` operations to create & update:
    * `Inode`s and their `Extent`s,
    * the path -> `Inode` mapping.

 - Run `finalize_inodes()` to condense the inodes' nested,
   history-preserving, clone-aware `Extent` objects into a test-friendly
   list of `Chunk`s.

   For testing, it is important to produce a representation that is as
   normalized as possible: our output should deterministically and uniquely
   capture the information we wish to test, and omit everything else[1].

   We do NOT want our output to depend on the order of the operations that
   created the filesystem, but only on the final filesystem state.

   Specifically:

    * For any byte offset[2] in the inode, we need to know whether it's a
      `HOLE`, or it contains `DATA` (see `Extent.Kind`).  An offset -> kind
      map is too verbose to use in manual tests, so we merge adjacent
      offsets with the same `Extent.Kind` into `Chunk`s.

    * For any offset in the inode, we need to know whether it is a clone of
      any other inode locations (i.e. copy-on-write sharing of underlying
      storage).  For this reason, each `Chunk` has a set of `ChunkClones`,
      which form a normalized[3] description of the shared-storage links on
      the filesystem.

      To give an example -- let's say that columns are byte offsets, and we
      have this 10-byte extent, parts of which were cloned to make inodes
      `A`, `B`, and `C`:

         BBBBBAAA
        AAACCCCC
        0123456789

      (Aside: This figure format is also used by `test_finalize_inodes`)

      Reading this figure, we see that:

       - A has a 6-byte DATA `Chunk` with two `ChunkClones`:
          * From `offset` 1 into B at `offset` 0 with length 2, aka `B:0+2@1`
          * From `offset` 3 into C at `offset` 3 with length 2, aka `C:3+2@3'

       - B has a 5-byte DATA `Chunk` with two `ChunkClones`:
          * From `offset` 0 into A at `offset` 1 with length 2, aka `A:1+2@0`
          * From `offset` 2 into C at `offset` 0 with length 3, aka `C:0+3@2'

       - C has a 5-byte DATA `Chunk` with two `ChunkClones`:
          * From `offset` 0 into B at `offset` 2 with length 3, aka `B:2+3@0`
          * From `offset` 3 into A at `offset` 3 with length 2, aka `A:3+2@3'

      You can see that our representation of "a set of `ChunkClone`s for
      every `Chunk`" is NOT parsimonious.  If the same range of bytes is
      cloned into N `Chunk`s, each of those `Chunk`s will refer to every
      other `Chunk`, for a total of N*(N-1)/2 references.  This is far less
      efficient than a spanning tree with `N - 1` references.

      E.g. in the above example, N = 4, and we stored 6 `ChunkClones`:

        {'A': {'B:0+2@1', 'C:3+2@3'},
         'B': {'A:1+2@0', 'C:0+3@2'},
         'C': {'B:2+3@0', 'A:3+2@3'}}

      The redundancy is obvious, e.g. each of these pairs are mirror images:
        - 'A': 'B:0+2@1'    versus    'B': 'A:1+2@0'
        - 'A': 'C:3+2@3'    versus    'C': 'A:3+2@3'
        - 'B': 'C:0+3@2'    versus    'C': 'B:2+3@0'
      Picking one ChunkClone from each line would make a 3-edge spanning tree.

      Using an inefficient presentation is an intentional design decision.
      In most test filesystems, the copy number of any Chunk will be low, so
      the cost of enumerating all references is minimal.  The upside of this
      quadratic representation is that it is unique and simple.

      In contrast, presenting the clone structure via a spanning tree breaks
      the symmetry, and then each test author has to understand the process
      by which the N-1 spanning tree edges are selected.  It's easy to make
      such a process deterministic, but it still adds cognitive load.

[1] The current code tracks clones of HOLEs, because it makes no effort to
    ignore them.  I would guess that btrfs lacks this tracking, since such
    clones would save no space.  Once this is confirmed, it would be very
    easy to either ignore, or leave unpopulated the `chunk_clones` field for
    `Chunk` object with `kind == Extent.Kind.HOLE`.

[2] I refer to "bytes" throughout, but in actuality filesystems are
    block-oriented.  To deal with this, divide all lengths and offsets by
    your block size to get the sense of "bytes" used here.

[3] The current code does NOT merge adjacent ChunkClones that were created
    by separate `clone` operations.  This is easy to fix once it comes up in
    real applications.  Tested in `test_cannot_merge_adjacent_clones()`.
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
    # set of `IncompleteInode.extent`s by `finalize_inodes`.
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
