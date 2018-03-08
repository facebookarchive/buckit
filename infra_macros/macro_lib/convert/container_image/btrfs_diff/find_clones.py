#!/usr/bin/env python3
'Please read the `file.py` docblock.'
# Future: frozentypes instead of NamedTuples can permit some cleanups below.
import functools

from collections import defaultdict
from typing import Dict, Iterable, NamedTuple, Sequence

from .extent import Extent
from .file import Clone, Chunk, ChunkClone, File


class _CloneExtentRef(NamedTuple):
    '''
    Connects a part of a HOLE/DATA leaf Extent to a location in some File.

    Although the Extent is shared between many files and/or disjoint
    locations in the same file, each _CloneExtentRef object is specific to
    one occurrence of this Extent in the `gen_trimmed_leaves` of one file.

    We initially create a _CloneExtentRef for every piece of every file, but
    later we only retain those have some inter-file overlap within their
    `.extent`, thus identifying cloned chunks of files.

    Aside: Unlike the simplified data model in `file.py`, the Extent's
    object identity captures the original reason that parts of some files
    became identified via a clone relationship.  We mostly use this for
    assertions.

    Future: With `frozentype`, __new__ could assert that `offset` and
    `clone.length` are sane with respect to `extent`.
    '''
    clone: Clone  # `clone.length` trims `extent`
    extent: Extent
    offset: int  # Trims `extent`
    # The position in `gen_trimmed_leaves` of the specific trimmed leaf that
    # is being connected to another file.
    #
    # It is possible for a File to have two instances of the same Extent
    # with the same offset & length in its `gen_trimmed_leaves` stream, see
    # e.g.  `test_multi_extent`.  In that case, we cannot correctly assign
    # `ChunkClone`s to their trimmed leaves based on the content of the
    # trimmed leaf: `(offset, length, extent)`.
    #
    # You might ask why the `ChunkClone` lists would differ between
    # identical trimmed extents?  Easy: the first has to refer to the
    # second, but not to itself, and conversely, the second must refer to
    # the first, but not to itself.
    #
    # We could avoid this denormalization by keying `CloneChunk`s on
    # `(file_offset, offset, length, extent)`, which is unique.  And
    # `gen_files_populating_chunks_and_clones` does already track
    # `file_offset`.  However, the denormalized approach seemed cleaner.
    leaf_idx: int

    def __repr__(self):  # pragma: no cover
        return (
            f'{self.clone.file.description}:{self.clone.offset}'
            f'+{self.clone.length}:{id(self.extent)}'  # Extent is too noisy
        )


# If these change, we have to update `_clone_op_compare_key`
assert Clone._fields.index('file') == 0
assert _CloneExtentRef._fields.index('clone') == 0


# Our _CloneOp ordering obeys the following invariants:
#  - sort by position first
#  - sort by action second, putting POPs before PUSHes (see their def'ns)
# We do not need finer-grained ordering because:
#  (1) we only do work on POPs,
#  (2) the work done on all the POPs at one position does not depend on the
#      order of the _CloneOps -- we symmetrically record the relationship in
#      both directions:
#        (just-popped op, each unpopped op)
#        (each unpopped op, just-popped op)
#
# We could get the desired ordering implicitly by:
#  - relying on the order of field declaration in `_CloneOp` (not bad)
#  - making `File`s comparable (way ugly)
# Luckily, being explicit is not *that* painful.
def _clone_op_compare_key(c: '_CloneOp'):
    return (
        # The preceding asserts make these [1:] hacks tolerable.
        c.pos, c.action, c.ref[1:], c.ref.clone[1:],
        # This final tie-breaker is non-deterministic from run to run, but
        # if the caller gave us two different files with identical
        # descriptions, there is nothing better to do.
        c.ref.clone.file.description, id(c.ref.clone.file)
    )


def _clone_op_compare(fn):
    @functools.wraps(fn)
    def cmp(self: '_CloneOp', other: '_CloneOp'):
        assert isinstance(other, _CloneOp)
        # We only compare ops within one extent. The tests assume this to
        # justify focusing on single-extent examples, so check it.
        assert self.ref.extent is other.ref.extent
        # All our items are distinct, since `clone.offset` is `file_offset`,
        # which is strictly increasing in each file.  We have no business
        # comparing a _CloneOp with itself.
        assert tuple.__ne__(self, other)
        return fn(_clone_op_compare_key(self), _clone_op_compare_key(other))
    return cmp


class _CloneOp(NamedTuple):
    PUSH = 'push'
    POP = 'pop'
    assert POP < PUSH  # We want to sort all POPs before any PUSHes

    pos: int
    action: str
    ref: _CloneExtentRef

    # NamedTuple confuses functools.total_ordering, so define all 6 comparators
    __eq__ = _clone_op_compare(tuple.__eq__)
    __ne__ = _clone_op_compare(tuple.__ne__)
    __lt__ = _clone_op_compare(tuple.__lt__)
    __le__ = _clone_op_compare(tuple.__le__)
    __gt__ = _clone_op_compare(tuple.__gt__)
    __ge__ = _clone_op_compare(tuple.__ge__)


def _leaf_extent_id_to_clone_ops(files: Iterable[File]):
    '''
    To collect the parts of a Chunk that are cloned, we do a variation on
    the standard interval-overlap algorithm.  We first sort the starts &
    ends of each interval, and then do a sequential scan that uses starts to
    add, and ends to remove, a tracking object from a "current intervals"
    structure.

    This function simply prepares the set of interval starts & ends for each
    file, the computation is in `_leaf_ref_to_chunk_clones_from_clone_ops`.
    '''
    leaf_extent_id_to_clone_ops = defaultdict(list)
    for f in files:
        file_offset = 0
        for leaf_idx, (offset, length, leaf_extent) in enumerate(
            f.extent.gen_trimmed_leaves()
        ):
            ref = _CloneExtentRef(
                clone=Clone(file=f, offset=file_offset, length=length),
                extent=leaf_extent,
                offset=offset,
                leaf_idx=leaf_idx,
            )
            leaf_extent_id_to_clone_ops[id(leaf_extent)].extend([
                _CloneOp(pos=offset, action=_CloneOp.PUSH, ref=ref),
                _CloneOp(pos=offset + length, action=_CloneOp.POP, ref=ref),
            ])
            file_offset += length
    return leaf_extent_id_to_clone_ops


def _leaf_ref_to_chunk_clones_from_clone_ops(
    extent_id: int, clone_ops: Iterable[_CloneOp]
):
    'As per `_leaf_extent_id_to_clone_ops`, this computes interval overlaps'
    active_ops: Dict[_CloneExtentRef, _CloneOp] = {}  # Tracks open intervals
    leaf_ref_to_chunk_clones = defaultdict(list)
    for op in sorted(clone_ops):
        # Whenever an interval (aka a File's Extent's "trimmed leaf") ends,
        # we create `ChunkClone` objects **to** and **from** all the
        # concurrently open intervals.
        if op.action is _CloneOp.POP:
            pushed_op = active_ops.pop(op.ref)
            assert pushed_op.ref is op.ref
            assert id(op.ref.extent) == extent_id
            assert pushed_op.pos == op.ref.offset
            assert pushed_op.pos + op.ref.clone.length == op.pos

            for clone_op in active_ops.values():
                assert op.ref.extent is clone_op.ref.extent

                # The cloned portion's extent offset is the larger of the 2
                bigger_offset = max(clone_op.ref.offset, op.ref.offset)

                # Record that `clone_op` clones part of `op`'s file.
                leaf_ref_to_chunk_clones[op.ref].append(ChunkClone(
                    offset=bigger_offset,
                    clone=Clone(
                        file=clone_op.ref.clone.file,
                        offset=clone_op.ref.clone.offset + (
                            bigger_offset - clone_op.ref.offset
                        ),
                        length=op.pos - bigger_offset,
                    ),
                ))

                # Record that `op` clones part of `clone_op`'s file.
                leaf_ref_to_chunk_clones[clone_op.ref].append(ChunkClone(
                    offset=bigger_offset,
                    clone=Clone(
                        file=op.ref.clone.file,
                        offset=op.ref.clone.offset + (
                            bigger_offset - op.ref.offset
                        ),
                        length=op.pos - bigger_offset,  # Same length
                    ),
                ))
        # Sorting guarantees all POPs for `pos` are handled before PUSHes
        elif op.action == _CloneOp.PUSH:
            assert op.ref not in active_ops
            active_ops[op.ref] = op
        else:
            assert False, op  # pragma: no cover
    return leaf_ref_to_chunk_clones


def _file_to_leaf_idx_to_chunk_clones(files: Iterable[File]):
    'Aggregates newly created ChunkClones per file, and per "trimmed leaf"'
    file_to_leaf_idx_to_chunk_clones = defaultdict(dict)
    for extent_id, clone_ops in _leaf_extent_id_to_clone_ops(files).items():
        leaf_ref_to_chunk_clones = _leaf_ref_to_chunk_clones_from_clone_ops(
            extent_id, clone_ops
        )
        for leaf_ref, offsets_clones in leaf_ref_to_chunk_clones.items():
            d = file_to_leaf_idx_to_chunk_clones[leaf_ref.clone.file]
            # A `leaf_idx` in a file has one extent, and each extent is
            # handled in one iteration, so it cannot be that two iterations
            # contribute to the same `leaf_idx` key.
            assert leaf_ref.leaf_idx not in d
            # `leaf_idx` is the position in `gen_trimmed_leaves` of the
            # chunk, whose clones we computed.  That fully specifies where
            #  `gen_files_populating_chunks_and_clones` should put the clones.
            d[leaf_ref.leaf_idx] = offsets_clones

    return file_to_leaf_idx_to_chunk_clones


def gen_files_populating_chunks_and_clones(files: Sequence[File]):
    '''
    Yields copies of `files` with `.chunks` populated. Raises if any
    `.chunks != None`.  Explained in detail in the docstring for `file.py`.
    '''
    # Don't make changes to files in which only some have populated chunks.
    for f in files:
        if f.chunks is not None:
            # This is saner than re-populating them, since the user might
            # get it into their head to call us with two different lists of
            # files, which would produce grossly inconsistent clone
            # detection results.  Of course, the better course of action is
            # to have Files be immutable, and to always make new objects.
            raise RuntimeError(f'{f}.chunks was already populated')

    f_to_leaf_idx_to_chunk_clones = _file_to_leaf_idx_to_chunk_clones(files)
    for f in files:
        leaf_to_chunk_clones = f_to_leaf_idx_to_chunk_clones.get(f, {})
        new_chunks = []
        for leaf_idx, (offset, length, extent) in enumerate(
            f.extent.gen_trimmed_leaves()
        ):
            chunk_clones = leaf_to_chunk_clones.get(leaf_idx, [])
            assert isinstance(extent.content, Extent.Kind)

            # If the chunk kind matches, merge into the previous chunk.
            if new_chunks and new_chunks[-1].kind == extent.content:
                prev_length = new_chunks[-1].length
                prev_clones = new_chunks[-1].chunk_clones
            else:  # Otherwise, make a new one.
                prev_length = 0
                prev_clones = set()
                new_chunks.append(None)

            new_chunks[-1] = Chunk(
                kind=extent.content,
                length=length + prev_length,
                chunk_clones=prev_clones,
            )
            new_chunks[-1].chunk_clones.update(
                # Future: when switching to frozentype, __new__ should
                # vaidate that clone offset & length are sane relative
                # to the trimmed extent.
                ChunkClone(
                    clone=clone,
                    # Subtract `offset` because `ChunkClone.offset` is
                    # Extent-relative, but in the actual file layout, the
                    # leaf Extent is trimmed further.
                    offset=clone_offset + prev_length - offset
                ) for clone_offset, clone in chunk_clones
            )
        yield f._replace(chunks=tuple(new_chunks))  # Future: deepfrozen?
