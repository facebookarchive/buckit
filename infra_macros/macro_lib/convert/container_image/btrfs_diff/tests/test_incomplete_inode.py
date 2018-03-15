#!/usr/bin/env python3
import stat
import unittest

from ..inode_id import InodeIDMap
from ..inode import InodeOwner, InodeUtimes
from ..incomplete_inode import (
    IncompleteDevice, IncompleteDir, IncompleteFifo, IncompleteFile,
    IncompleteSocket, IncompleteSymlink,
)
from ..parse_dump import SendStreamItem, SendStreamItems


class IncompleteInodeTestCase(unittest.TestCase):

    def test_incomplete_file_including_common_attributes(self):
        ino = IncompleteFile(
            item=SendStreamItems.mkfile(path=b'a'), id_map=InodeIDMap(),
        )

        self.assertEqual('(IncompleteFile: a/0)', repr(ino))

        self.assertEqual({}, ino.xattrs)
        self.assertIs(None, ino.owner)
        self.assertIs(None, ino.mode)
        self.assertIs(None, ino.utimes)
        self.assertEqual(stat.S_IFREG, ino.file_type)

        ino.apply_item(SendStreamItems.truncate(path=b'a', size=17))
        self.assertEqual('(IncompleteFile: a/17)', repr(ino))

        ino.apply_item(
            SendStreamItems.write(path=b'a', offset=10, data=b'x' * 15)
        )
        self.assertEqual('(IncompleteFile: a/25)', repr(ino))

        ino.apply_item(
            SendStreamItems.update_extent(path=b'a', offset=40, len=5)
        )
        self.assertEqual('(IncompleteFile: a/45)', repr(ino))

        ino.apply_item(
            SendStreamItems.set_xattr(path=b'a', name=b'cat', data=b'nip')
        )
        self.assertEqual({b'cat': b'nip'}, ino.xattrs)

        ino.apply_item(SendStreamItems.remove_xattr(path=b'a', name=b'cat'))
        self.assertEqual({}, ino.xattrs)

        with self.assertRaisesRegex(KeyError, 'cat'):
            ino.apply_item(SendStreamItems.remove_xattr(path=b'a', name=b'cat'))

        # Test the `setuid` bit while we are at it.
        ino.apply_item(SendStreamItems.chmod(path=b'a', mode=0o4733))
        self.assertEqual(0o4733, ino.mode)

        with self.assertRaisesRegex(RuntimeError, 'cannot change file type'):
            ino.apply_item(SendStreamItems.chmod(path=b'a', mode=0o104733))

        ino.apply_item(SendStreamItems.chown(path=b'a', uid=1000, gid=2000))
        self.assertEqual(InodeOwner(uid=1000, gid=2000), ino.owner)

        ino.apply_item(
            SendStreamItems.utimes(path=b'a', ctime=1., mtime=2., atime=3.)
        )
        self.assertEqual(InodeUtimes(ctime=1., mtime=2., atime=3.), ino.utimes)

        class FakeItem(metaclass=SendStreamItem):
            pass

        with self.assertRaisesRegex(RuntimeError, 'cannot apply FakeItem'):
            ino.apply_item(FakeItem(path=b'a'))

    # These have no special logic, so this exercise is mildly redundant,
    # but hey, unexecuted Python is a dead, smelly, broken Python.
    def test_simple_file_types(self):
        for item_type, file_type, inode_type in (
            (SendStreamItems.mkdir, stat.S_IFDIR, IncompleteDir),
            (SendStreamItems.mkfifo, stat.S_IFIFO, IncompleteFifo),
            (SendStreamItems.mksock, stat.S_IFSOCK, IncompleteSocket),
        ):
            ino = inode_type(item=item_type(path=b'a'), id_map=InodeIDMap())
            self.assertEqual(f'({inode_type.__name__}: a)', repr(ino))
            self.assertEqual(file_type, ino.file_type)

    def test_devices(self):
        ino_chr = IncompleteDevice(
            item=SendStreamItems.mknod(path=b'chr', mode=0o20711, dev=123),
            id_map=InodeIDMap(),
        )
        self.assertEqual(stat.S_IFCHR, ino_chr.file_type)
        self.assertEqual(123, ino_chr.dev)
        self.assertEqual(0o711, ino_chr.mode)

        ino_blk = IncompleteDevice(
            item=SendStreamItems.mknod(path=b'blk', mode=0o60544, dev=345),
            id_map=InodeIDMap(),
        )
        self.assertEqual(stat.S_IFBLK, ino_blk.file_type)
        self.assertEqual(345, ino_blk.dev)
        self.assertEqual(0o544, ino_blk.mode)

        with self.assertRaisesRegex(RuntimeError, 'unexpected device mode'):
            IncompleteDevice(
                item=SendStreamItems.mknod(path=b'e', mode=0o10644, dev=3),
                id_map=InodeIDMap(),
            )

    def test_symlink(self):
        ino = IncompleteSymlink(
            item=SendStreamItems.symlink(path=b'l', dest=b'cat'),
            id_map=InodeIDMap(),
        )

        self.assertEqual(stat.S_IFLNK, ino.file_type)
        self.assertEqual(b'cat', ino.dest)

        self.assertEqual(None, ino.owner)
        ino.apply_item(SendStreamItems.chown(path=b'l', uid=1, gid=2))
        self.assertEqual(InodeOwner(uid=1, gid=2), ino.owner)

        self.assertEqual(None, ino.mode)
        with self.assertRaisesRegex(RuntimeError, 'cannot chmod symlink'):
            ino.apply_item(SendStreamItems.chmod(path=b'l', mode=0o644))


if __name__ == '__main__':
    unittest.main()
