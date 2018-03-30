#!/usr/bin/env python3
'''
A `SubvolumeSet` maps path subtrees to `Subvolume`s. Therefore, it only
knows how to apply the initial `SendStreamItems` types that set the
subvolume for the rest of the stream.

Note that at present, `Subvolume`s are **not** mounted into a shared
directory tree the way they would be in a real btrfs filesystem.  This is
not done here simply because we don't have a need to model it, but you can
easily imagine a path-aware `Volume` abstraction on top of this.
'''
import copy

from collections import Counter
# Future: `deepfrozen` would let us lose the `new` methods on NamedTuples,
# and avoid `deepcopy`.
from typing import Mapping, NamedTuple, Optional

from .inode_id import InodeIDMap
from .send_stream import SendStreamItem, SendStreamItems
from .subvolume import Subvolume


class SubvolumeID(NamedTuple):
    uuid: str
    # NB: in principle, we might want to check that the transaction ID
    # matches that of the `clone` command, to increase the odds that we are
    # cloning the bits we expect to be cloning.  However, at the time of
    # writing, `btrfs-progs` does not perform this check.  To add this check
    # here, we'd need to make sure that the transaction ID is meaningfully
    # updated as a send-stream is applied.  This seems problematic, since
    # the organically obtained transaction ID on the source volume need not
    # have any correspondence to the number of transactions encoded in the
    # send-stream -- a send-stream might encode the same filesystem changes
    # in fewer or more transactions than did the underlying VFS commands.
    # Thereforeo, the only context in which it is meaningful to check
    # transaction IDs is when the parent was built up from the same exact
    # sequence of diffs on both the sending & the receiving side.  Achieving
    # this would involve re-applying each diffs at build-time, which besides
    # code complexity may incur some performance overhead.
    transid: int


class SubvolumeDescription(NamedTuple):
    '''
    This is a "cheat" to make debugging & testing easier, but it is NOT part
    of the core data model.  If you are caught using it in real business
    logic, you will be asked to wear a red nose and/or a cone of shame.

    In particular, these fields are deliberately NOT on `Subvolume` because
    only `SubvolumeSet` should know the context in which the `Subvolume`
    exists.

    We give store this as `InodeIDMap.description` to make it easy to
    distinguish between `InodeID`s from different `Subvolume`s.

    IMPORTANT: Because of our `.name_uuid_prefix_counts` member, which is
    owned by a `SubvolumeSet`, this object would ONLY be safely
    `deepcopy`able if we were to copy the `SubvolumeSet` in one call -- but
    we never do that.  When we make snapshots in `SubvolumeSetMutator`, we
    have to work around this problem, since a naive implementation would
    `deepcopy` this object via `Subvolume.id_map.description`.
    '''
    name: bytes
    id: SubvolumeID
    parent_id: Optional[SubvolumeID]
    # See the IMPORTANT note in the docblock about this member:
    name_uuid_prefix_counts: Mapping[str, int]

    def name_uuid_prefixes(self):
        name = self.name.decode(errors='surrogateescape')
        for i in range(len(self.id.uuid) + 1):
            yield (name + '@' + self.id.uuid[:i]) if i else name

    def __repr__(self):
        for prefix in self.name_uuid_prefixes():
            if self.name_uuid_prefix_counts.get(prefix, 0) < 2:
                return prefix
        # Happens when one uuid is a prefix of another, i.e. in tests.
        return f'{prefix}-ERROR'


class SubvolumeSet(NamedTuple):
    uuid_to_subvolume: Mapping[str, Subvolume]
    # `SubvolumeDescription` wants to represent itself as `name@abc`, where
    # `abc` is the shortest prefix of its UUID that uniquely identifies it
    # within the `SubvolumeSet`.  In order to make it easy to find this
    # shortest prefix, we keep track of the count of `name@uuid_prefix` for
    # each possible length of prefix (from 0 to `len(uuid)`).  When the name
    # is unique, `@uuid_prefix` is omitted (aka prefix length 0).
    name_uuid_prefix_counts: Mapping[str, int]

    @classmethod
    def new(cls, **kwargs) -> 'SubvolumeSet':
        kwargs.setdefault('uuid_to_subvolume', {})
        kwargs.setdefault('name_uuid_prefix_counts', Counter())
        return cls(**kwargs)


class SubvolumeSetMutator(NamedTuple):
    '''
    A send-stream always starts with a command defining the subvolume,
    to which the remaining stream commands will be applied.  Since
    `SubvolumeSet` is only responsible for managing `Subvolume`s, this
    is essentially a proxy for `Subvolume.apply_item`.

    The reason we don't just return `Subvolume` to the caller after
    the first item is that we need some logic as the `SubvolumeSet` and
    `Subvolume` layers to resolve `clone` commands.
    '''
    subvolume: Subvolume
    subvolume_set: SubvolumeSet

    @classmethod
    def new(
        cls, subvol_set: SubvolumeSet, subvol_item: SendStreamItem,
    ) -> 'SubvolumeSetMutator':
        if not isinstance(subvol_item, (
            SendStreamItems.subvol, SendStreamItems.snapshot,
        )):
            raise RuntimeError(f'{subvol_item} must specify subvolume')

        my_id = SubvolumeID(uuid=subvol_item.uuid, transid=subvol_item.transid)
        parent_id = SubvolumeID(
            uuid=subvol_item.parent_uuid,
            transid=subvol_item.parent_transid,
        ) if isinstance(subvol_item, SendStreamItems.snapshot) else None
        description = SubvolumeDescription(
            name=subvol_item.path, id=my_id, parent_id=parent_id,
            name_uuid_prefix_counts=subvol_set.name_uuid_prefix_counts,
        )
        if isinstance(subvol_item, SendStreamItems.snapshot):
            parent_subvol = subvol_set.uuid_to_subvolume[parent_id.uuid]
            # `SubvolumeDescription` contains `SubvolumeSet`, so it is not
            # correctly `deepcopy`able.  And since we immediately overwrite
            # the `description`, it would be quite wasteful to copy its
            # entire `SubvolumeSet` just to throw it away.
            old_description = parent_subvol.id_map.description
            try:
                parent_subvol.id_map.description = None
                subvol = copy.deepcopy(parent_subvol)
                subvol.id_map.description = description
            finally:
                parent_subvol.id_map.description = old_description
        else:
            subvol = Subvolume.new(id_map=InodeIDMap(description=description))

        dup_subvol = subvol_set.uuid_to_subvolume.get(my_id.uuid)
        if dup_subvol is not None:
            raise RuntimeError(f'{my_id} is already in use: {dup_subvol}')
        subvol_set.uuid_to_subvolume[my_id.uuid] = subvol

        # insertion can fail, so update the description disambiguator last.
        subvol_set.name_uuid_prefix_counts.update(
            description.name_uuid_prefixes()
        )

        return cls(subvolume=subvol, subvolume_set=subvol_set)

    def apply_item(self, item: SendStreamItem):
        if isinstance(item, SendStreamItems.clone):
            from_subvol = self.subvolume_set.uuid_to_subvolume.get(
                item.from_uuid
            )
            if not from_subvol:
                raise RuntimeError(f'Unknown from_uuid for {item}')
            return self.subvolume.apply_clone(item, from_subvol)
        return self.subvolume.apply_item(item)
