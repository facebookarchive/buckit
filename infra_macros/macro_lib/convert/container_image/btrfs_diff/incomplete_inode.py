#!/usr/bin/env python3
'''
To construct our filesystem, it is convenient to have mutable classes that
track the state-in-progress.  The `IncompleteInode` hierarchy stores that
state, and knows how to apply parsed `SendStreamItems` to mutate the state.

Once the filesystem is done, we will "freeze" it into immutable, hashable,
easily comparable `Inode` objects, making it a "breeze" to validate it.

IMPORTANT: Keep these objects correctly `deepcopy`able. That is the case at
the time of writing because:
 - `Extent` is recursively immutable and customizes copy operations to
   return the original object -- this lets us correctly track clones.
 - All other attributes store plain-old-data, or POD immutable classes that
   do not care about object identity.

Future: with `deepfrozen` done, it would be simplest to merge
`IncompleteInode` with `Inode`, and just have `apply_item` return a
partly-modified copy, in the style of `NamedTuple._replace`.
'''
import stat

from typing import Dict, Optional

from .extent import Extent
from .inode_id import InodeID, InodeIDMap
from .inode import InodeOwner, InodeUtimes, S_IFMT_TO_FILE_TYPE_NAME
from .parse_dump import SendStreamItem, SendStreamItems


class IncompleteInode:
    '''
    Base class for all inode types. Inheritance is appropriate because
    different inode types have different data, different construction logic,
    and finalization logic.
    '''
    id: InodeID  # The final `Inode` object inherits this ID.
    xattrs: Dict[bytes, bytes]
    # If any of these are None, the filesystem was created badly.
    # Exception: symlinks don't have permissions.
    owner: Optional[InodeOwner]
    mode: Optional[int]  # Bottom 12 bits of `st_mode`
    file_type: int  # Upper bits of `st_mode` matching `S_IFMT`
    utimes: Optional[InodeUtimes]

    def __init__(self, *, item: SendStreamItem, id_map: InodeIDMap):
        assert isinstance(item, self.INITIAL_ITEM)
        self.id = id_map.next(item.path)
        self.xattrs = {}
        self.owner = None
        self.mode = None
        self.utimes = None
        self.file_type = self.FILE_TYPE

    def apply_item(self, item: SendStreamItem) -> None:
        if isinstance(item, SendStreamItems.remove_xattr):
            del self.xattrs[item.name]
        elif isinstance(item, SendStreamItems.set_xattr):
            self.xattrs[item.name] = item.data
        elif isinstance(item, SendStreamItems.chmod):
            if stat.S_IFMT(item.mode) != 0:
                raise RuntimeError(
                    f'{item} cannot change file type bits of {self}'
                )
            self.mode = item.mode
        elif isinstance(item, SendStreamItems.chown):
            self.owner = InodeOwner(uid=item.uid, gid=item.gid)
        elif isinstance(item, SendStreamItems.utimes):
            self.utimes = InodeUtimes(
                ctime=item.ctime,
                mtime=item.mtime,
                atime=item.atime,
            )
        else:
            raise RuntimeError(f'{self} cannot apply {item}')

    def _repr_fields(self):
        if self.owner is not None:
            yield f'o{self.owner}'
        if self.mode is not None:
            yield f'm{self.mode:o}'
        if self.utimes is not None:
            yield f't{self.utimes}'

    def __repr__(self):
        return '(' + ' '.join([
            S_IFMT_TO_FILE_TYPE_NAME.get(self.FILE_TYPE, self.FILE_TYPE),
            repr(self.id),
            *self._repr_fields(),
        ]) + ')'


class IncompleteDir(IncompleteInode):
    FILE_TYPE = stat.S_IFDIR
    INITIAL_ITEM = SendStreamItems.mkdir


class IncompleteFile(IncompleteInode):
    extent: Extent

    FILE_TYPE = stat.S_IFREG
    INITIAL_ITEM = SendStreamItems.mkfile

    def __init__(self, *, item: SendStreamItem, id_map: InodeIDMap):
        super().__init__(item=item, id_map=id_map)
        self.extent = Extent.empty()

    def apply_item(self, item: SendStreamItem) -> None:
        if isinstance(item, SendStreamItems.clone):
            # Temporary: added in the stack after the Subvolume diff.
            raise NotImplementedError  # pragma: no cover
        elif isinstance(item, SendStreamItems.truncate):
            self.extent = self.extent.truncate(length=item.size)
        elif isinstance(item, SendStreamItems.write):
            self.extent = self.extent.write(
                offset=item.offset, length=len(item.data),
            )
        elif isinstance(item, SendStreamItems.update_extent):
            self.extent = self.extent.write(
                offset=item.offset, length=item.len,
            )
        else:
            super().apply_item(item=item)

    def _repr_fields(self):
        yield from super()._repr_fields()
        if self.extent.length:
            yield f'{self.extent}'


class IncompleteSocket(IncompleteInode):
    FILE_TYPE = stat.S_IFSOCK
    INITIAL_ITEM = SendStreamItems.mksock


class IncompleteFifo(IncompleteInode):
    FILE_TYPE = stat.S_IFIFO
    INITIAL_ITEM = SendStreamItems.mkfifo


class IncompleteDevice(IncompleteInode):
    dev: int

    INITIAL_ITEM = SendStreamItems.mknod

    def __init__(self, *, item: SendStreamItem, id_map: InodeIDMap):
        self.FILE_TYPE = stat.S_IFMT(item.mode)
        if self.FILE_TYPE not in (stat.S_IFBLK, stat.S_IFCHR):
            raise RuntimeError(f'unexpected device mode in {item}')
        super().__init__(item=item, id_map=id_map)
        # NB: At present, `btrfs send` redundantly sends a `chmod` after
        # device creation, but we've already saved the file type.
        self.mode = item.mode & ~self.FILE_TYPE
        self.dev = item.dev

    def _repr_fields(self):
        yield from super()._repr_fields()
        yield f'{hex(self.dev)[2:]}'


class IncompleteSymlink(IncompleteInode):
    dest: bytes

    FILE_TYPE = stat.S_IFLNK
    INITIAL_ITEM = SendStreamItems.symlink

    def __init__(self, *, item: SendStreamItem, id_map: InodeIDMap):
        super().__init__(item=item, id_map=id_map)
        self.dest = item.dest

    def apply_item(self, item: SendStreamItem) -> None:
        if isinstance(item, SendStreamItems.chmod):
            raise RuntimeError(f'{item} cannot chmod symlink {self}')
        else:
            super().apply_item(item=item)

    def _repr_fields(self):
        yield from super()._repr_fields()
        yield f'{self.dest.decode(errors="surrogateescape")}'
