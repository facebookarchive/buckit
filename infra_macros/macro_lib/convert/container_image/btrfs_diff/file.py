#!/usr/bin/env python3
'''
The workflow for creating a mock filesystem is as follows:

 - Sequentially apply `btrfs send` operations to create & update:
    * `File`s and their `Extent`s,
    * the path -> `File` mapping.

 - Run `find_clones.gen_files_populating_chunks_and_clones()` to condense the
   files' nested, history-preserving, clone-aware `Extent` objects into a
   test-friendly list of `Chunk`s.

   For testing, it is important to produce a representation that is as
   normalized as possible: our output should deterministically and uniquely
   capture the information we wish to test, and omit everything else[1].

   We do NOT want our output to depend on the order of the operations that
   created the filesystem, but only on the final filesystem state.

   Specifically:

    * For any byte[2] in the file, we need to know whether it's a `HOLE`, or
      it contains `DATA` (see `Extent.Kind`).  A byte -> kind map is too
      verbose to use in manual tests, so we merge adjacent bytes with the
      same `Extent.Kind` into `Chunk`s.

    * For any byte in the file, we need to know whether it is a clone of
      any other file locations (i.e. copy-on-write sharing of underlying
      storage).  For this reason, each `Chunk` has a set of `ChunkClones`,
      which form a normalized[3] description of the shared-storage links on
      the filesystem.

      To give an example -- let's say that columns are byte offsets, and we
      have this 10-byte extent, parts of which were cloned to make files
      `A`, `B`, and `C`:

         BBBBBAAA
        AAACCCCC
        0123456789

      (Aside: This figure format is also used by `test_find_clones`)

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
    real applications.  See the 'bbaa\naabb' example in
    `test_simple_figures()`,
'''
from typing import NamedTuple, Set, Optional, Sequence

from .extent import Extent


class File(NamedTuple):
    # Why is this `description` and not `name` or `path`? To support
    # hardlinks, a `File` object must effectively be a nameless inode.
    # However, it is really useful to be able to put **something** into the
    # structure to be used as a debugging identifier.  In tests, these are
    # short strings, in mock filesystems, we might use an autoincrement
    # integer plus one of the inode's paths.
    description: str
    extent: Extent

    # The file data is a concatenation of Chunks. Once the filesystem is
    # ready, `gen_files_populating_chunks_and_clones` populates this.
    chunks: Optional[Sequence['Chunk']] = None

    def __repr__(self):
        return f'(File: {self.description}/{self.extent.length})'


class Clone(NamedTuple):
    'A reference to a byte interval in another file.'
    file: File
    offset: int  # The first byte in `file` of the cloned part of the Chunk
    length: int  # Length of the cloned part of the Chunk

    def __repr__(self):
        return f'{self.file.description}:{self.offset}+{self.length}'


class ChunkClone(NamedTuple):
    # Clones are only parts of a chunk. The offset of the clone within this
    # chunk is outside of `Clone` to simplify chunk merging.
    offset: int  # Offset into the `Chunk`
    clone: Clone  # What file + location is this a clone of?

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
