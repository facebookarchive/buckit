#!/usr/bin/env python3
'''
Much of the data in our mock VFS layer lies at the level of inodes
(see `incomplete_inode.py`, `inode.py`, etc).  `Subvolume` in the
next level up -- it maps paths to inodes.

Just like `IncompleteInode`, it knows how to apply `SendStreamItems` to
mutate its state.

## Known issues

- For now, we model subvolumes as having completely independent path
  structures.  They are not "mounted" into any kind of common directory
  tree, so our code does not currently need to check if a path inside a
  subvolume actually belongs to an inner subvolume.  In particular, this
  means we don't need to check for cross-device hardlinks or renames.

- Right now, we assume that all paths are fully resolved (symlink path
  components do not work)This is true for btrfs send-streams.  However, a
  truly general VFS mock would resolve symlinks in path components as
  specified by the standard.

- Maximum path lengths are not checked.
'''
from typing import Mapping, NamedTuple, Optional

from .inode_id import InodeID, InodeIDMap
from .incomplete_inode import (
    IncompleteDevice, IncompleteDir, IncompleteFifo, IncompleteFile,
    IncompleteInode, IncompleteSocket, IncompleteSymlink,
)
from .send_stream import SendStreamItem, SendStreamItems

_DUMP_ITEM_TO_INCOMPLETE_INODE = {
    SendStreamItems.mkdir: IncompleteDir,
    SendStreamItems.mkfile: IncompleteFile,
    SendStreamItems.mksock: IncompleteSocket,
    SendStreamItems.mkfifo: IncompleteFifo,
    SendStreamItems.mknod: IncompleteDevice,
    SendStreamItems.symlink: IncompleteSymlink,
}


# Future: `deepfrozen` would let us lose the `new` methods on NamedTuples,
# and avoid `deepcopy`.
class Subvolume(NamedTuple):
    '''
    Models a btrfs subvolume, knows how to apply SendStreamItem mutations
    to itself.

    IMPORTANT: Keep this object correctly `deepcopy`able, we need that
    for snapshotting. Notes:

      - `InodeIDMap` opaquely holds a `description`, which in practice
        is a `SubvolumeDescription` that is **NOT** safely `deepcopy`able
        unless the whole `Volume` is being copied in one call.  For
        single-volume snapshots, `ApplySendStreamToVolume` has an icky
        workaround :)

      - The tests for `InodeIDMap` try to ensure that it is safely
        `deepcopy`able.  Changes to its members should be validated there.

      - Any references to `id_map` from inside `id_to_node` are handled
        correctly, since we copy the entire `Subvolume` object in a single
        operation and `deepcopy` understands object aliasing.

      - `IncompleteInode` descendants are correctly deepcopy-able despite
        the fact that `Extent` relies on object identity for clone-tracking.
        This is explained in the submodule docblock.
    '''
    # Inodes & inode maps are per-subvolume because btrfs treats subvolumes
    # as independent entities -- we cannot `rename` or hard-link data across
    # subvolumes, both fail with `EXDEV (Invalid cross-device link)`.
    # (Aside: according to Chris Mason, this is required to enable correct
    # space accounting on a per-subvolume basis.) The only caveat to this is
    # that a cross-subvolume `rename` is permitted to change the location
    # where a subvolume is mounted within a volume, but this does not
    # require us to share inodes across subvolumes.
    id_map: InodeIDMap
    id_to_inode: Mapping[InodeID, IncompleteInode]

    @classmethod
    def new(cls, *, id_map, **kwargs) -> 'Subvolume':
        kwargs.setdefault('id_to_inode', {})
        kwargs['id_to_inode'][id_map.get_id(b'.')] = IncompleteDir(
            item=SendStreamItems.mkdir(path=b'.'),
        )
        return cls(id_map=id_map, **kwargs)

    def inode_at_path(self, path) -> Optional[IncompleteInode]:
        id = self.id_map.get_id(path)
        # Using `[]` instead of `.get()` to assert that `id_to_inode`
        # remains a superset of `id_map`.  The converse is harder to check.
        return None if id is None else self.id_to_inode[id]

    def _delete(self, path):
        ino_id = self.id_map.remove_path(path)
        if not self.id_map.get_paths(ino_id):
            del self.id_to_inode[ino_id]

    def apply_item(self, item: SendStreamItem) -> None:
        for item_type, inode_class in _DUMP_ITEM_TO_INCOMPLETE_INODE.items():
            if isinstance(item, item_type):
                ino_id = self.id_map.next(item.path)
                assert ino_id not in self.id_to_inode
                self.id_to_inode[ino_id] = inode_class(item=item)
                return  # Done applying item

        if isinstance(item, SendStreamItems.rename):
            if item.dest.startswith(item.path + b'/'):
                raise RuntimeError(f'{item} makes path its own subdirectory')

            old_id = self.id_map.get_id(item.path)
            if old_id is None:
                raise RuntimeError(f'source of {item} does not exist')
            new_id = self.id_map.get_id(item.dest)

            # Per `rename (2)`, renaming same-inode links has NO effect o_O
            if old_id == new_id:
                return

            # No destination path? Easy.
            if new_id is None:
                self.id_map.add_path(
                    self.id_map.remove_path(item.path), item.dest,
                )
                return

            # Overwrite an existing path.
            if isinstance(self.id_to_inode[old_id], IncompleteDir):
                new_ino = self.id_to_inode[new_id]
                # _delete() below will ensure that the destination is empty
                if not isinstance(new_ino, IncompleteDir):
                    raise RuntimeError(
                        f'{item} cannot overwrite {new_ino}, since a '
                        'directory may only overwrite an empty directory'
                    )
            elif isinstance(self.id_to_inode[new_id], IncompleteDir):
                raise RuntimeError(
                    f'{item} cannot overwrite a directory with a non-directory'
                )
            self._delete(item.dest)
            self.id_map.add_path(self.id_map.remove_path(item.path), item.dest)
            # NB: Per `rename (2)`, if either the new or the old inode is a
            # symbolic link, they get treated just as regular files.
        elif isinstance(item, SendStreamItems.unlink):
            if isinstance(self.inode_at_path(item.path), IncompleteDir):
                raise RuntimeError(f'Cannot {item} a directory')
            self._delete(item.path)
        elif isinstance(item, SendStreamItems.rmdir):
            if not isinstance(self.inode_at_path(item.path), IncompleteDir):
                raise RuntimeError(f'Can only {item} a directory')
            self._delete(item.path)
        elif isinstance(item, SendStreamItems.link):
            if self.id_map.get_id(item.dest) is not None:
                raise RuntimeError(f'Destination of {item} already exists')
            old_id = self.id_map.get_id(item.path)
            if old_id is None:
                raise RuntimeError(f'{item} source does not exist')
            if isinstance(self.id_to_inode[old_id], IncompleteDir):
                raise RuntimeError(f'Cannot {item} a directory')
            self.id_map.add_path(old_id, item.dest)
        else:  # Any other operation must be handled at inode scope.
            ino = self.inode_at_path(item.path)
            if ino is None:
                raise RuntimeError(f'Cannot apply {item}, path does not exist')
            ino.apply_item(item=item)
