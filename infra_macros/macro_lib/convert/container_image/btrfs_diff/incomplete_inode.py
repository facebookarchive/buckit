#!/usr/bin/env python3
'''
To construct our filesystem, it is convenient to have mutable classes that
track the state-in-progress.  The `IncompleteInode` hierarchy stores that
state, and knows how to apply parsed `DumpItems` to mutate the state.

Once the filesystem is done, we will "freeze" it into immutable, hashable,
easily comparable `Inode` objects, making it a "breeze" to validate it.
'''
import stat

from typing import Dict, Optional

from .extent import Extent
from .inode_id import InodeID, InodeIDMap
from .inode import InodeOwner, InodeUtimes
from .parse_dump import DumpItem, DumpItems


# Future: with `deepfrozen` done, it'd be interesting to see if using a
# "freezabletype" idiom makes the Inode/IncompleteInode split clearer.
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

    def __init__(self, *, item: DumpItem, id_map: InodeIDMap):
        assert isinstance(item, self.INITIAL_ITEM)
        self.id = id_map.next([item.path])
        self.xattrs = {}
        self.owner = None
        self.mode = None
        self.utimes = None
        self.file_type = self.FILE_TYPE

    def apply_item(self, item: DumpItem) -> None:
        if isinstance(item, DumpItems.remove_xattr):
            del self.xattrs[item.name]
        elif isinstance(item, DumpItems.set_xattr):
            self.xattrs[item.name] = item.data
        elif isinstance(item, DumpItems.chmod):
            if stat.S_IFMT(item.mode) != 0:
                raise RuntimeError(
                    f'{item} cannot change file type bits of {self}'
                )
            self.mode = item.mode
        elif isinstance(item, DumpItems.chown):
            self.owner = InodeOwner(uid=item.uid, gid=item.gid)
        elif isinstance(item, DumpItems.utimes):
            self.utimes = InodeUtimes(
                ctime=item.ctime,
                mtime=item.mtime,
                atime=item.atime,
            )
        else:
            raise RuntimeError(f'{self} cannot apply {item}')

    def __repr__(self):
        return f'({type(self).__name__}: {self.id})'


class IncompleteDir(IncompleteInode):
    FILE_TYPE = stat.S_IFDIR
    INITIAL_ITEM = DumpItems.mkdir


class IncompleteFile(IncompleteInode):
    extent: Extent

    FILE_TYPE = stat.S_IFREG
    INITIAL_ITEM = DumpItems.mkfile

    def __init__(self, *, item: DumpItem, id_map: InodeIDMap):
        super().__init__(item=item, id_map=id_map)
        self.extent = Extent.empty()

    def apply_item(self, item: DumpItem) -> None:
        if isinstance(item, DumpItems.clone):
            # Temporary: added in the stack after the Subvolume diff.
            raise NotImplementedError  # pragma: no cover
        elif isinstance(item, DumpItems.truncate):
            self.extent = self.extent.truncate(length=item.size)
        elif isinstance(item, (DumpItems.write, DumpItems.update_extent)):
            self.extent = self.extent.write(
                offset=item.offset, length=item.len,
            )
        else:
            super().apply_item(item=item)

    def __repr__(self):
        # clone-finding tests use the length as an extra sanity check.
        return f'({type(self).__name__}: {self.id}/{self.extent.length})'


class IncompleteSocket(IncompleteInode):
    FILE_TYPE = stat.S_IFSOCK
    INITIAL_ITEM = DumpItems.mksock


class IncompleteFifo(IncompleteInode):
    FILE_TYPE = stat.S_IFIFO
    INITIAL_ITEM = DumpItems.mkfifo


class IncompleteDevice(IncompleteInode):
    dev: int

    INITIAL_ITEM = DumpItems.mknod

    def __init__(self, *, item: DumpItem, id_map: InodeIDMap):
        self.FILE_TYPE = stat.S_IFMT(item.mode)
        if self.FILE_TYPE not in (stat.S_IFBLK, stat.S_IFCHR):
            raise RuntimeError(f'unexpected device mode in {item}')
        super().__init__(item=item, id_map=id_map)
        # NB: At present, `btrfs send` redundantly sends a `chmod` after
        # device creation, but we've already saved the file type.
        self.mode = item.mode & ~self.FILE_TYPE
        self.dev = item.dev


class IncompleteSymlink(IncompleteInode):
    dest: bytes

    FILE_TYPE = stat.S_IFLNK
    INITIAL_ITEM = DumpItems.symlink

    def __init__(self, *, item: DumpItem, id_map: InodeIDMap):
        super().__init__(item=item, id_map=id_map)
        self.dest = item.dest

    def apply_item(self, item: DumpItem) -> None:
        if isinstance(item, DumpItems.chmod):
            raise RuntimeError(f'{item} cannot chmod symlink {self}')
        else:
            super().apply_item(item=item)
