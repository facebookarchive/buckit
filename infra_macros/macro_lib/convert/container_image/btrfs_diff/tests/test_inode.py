#!/usr/bin/env python3
import stat
import unittest

from ..extent import Extent
from ..inode import Chunk, ChunkClone, Clone, Inode, InodeOwner, InodeUtimes
from ..inode_id import InodeIDMap


class InodeTestCase(unittest.TestCase):

    def _inode(self, st_mode, **kwargs):
        return Inode._new(
            id=InodeIDMap().next('path'),
            st_mode=st_mode,
            owner=InodeOwner(uid=3, gid=5),
            utimes=InodeUtimes(ctime=8., mtime=13., atime=21.),
            **kwargs,
        )

    def test_inode(self):
        ino_file = self._inode(stat.S_IFREG | 0o640, chunks=())
        self.assertEqual('(File: path)', repr(ino_file))
        self.assertIsNotNone(ino_file.chunks)
        self.assertIsNone(ino_file.dev)
        self.assertIsNone(ino_file.dest)

        ino_block = self._inode(stat.S_IFBLK | 0o444, dev=123)
        self.assertEqual('(Block: path)', repr(ino_block))
        self.assertIsNone(ino_block.chunks)
        self.assertIsNotNone(ino_block.dev)
        self.assertIsNone(ino_block.dest)

        ino_link = self._inode(stat.S_IFLNK, dest='foo')
        self.assertEqual('(Symlink: path)', repr(ino_link))
        self.assertIsNone(ino_link.chunks)
        self.assertIsNone(ino_link.dev)
        self.assertIsNotNone(ino_link.dest)

        # Symlinks must canonically have permissions set to 0
        with self.assertRaises(AssertionError):
            self._inode(stat.S_IFLNK | 0o644, dest='foo')

        # Trip each of the "optional args" assertions
        for kwargs in [
            {'st_mode': stat.S_IFREG},
            {'st_mode': stat.S_IFCHR},
            {'st_mode': stat.S_IFBLK},
            {'st_mode': stat.S_IFLNK},
            {'st_mode': stat.S_IFREG, 'chunks': (), 'dev': 123},
            {'st_mode': stat.S_IFCHR, 'dev': 123, 'dest': b'o'},
            {'st_mode': stat.S_IFBLK, 'dev': 123, 'dest': b'o'},
            {'st_mode': stat.S_IFBLK, 'dest': 123, 'chunks': ()},
        ]:
            with self.assertRaises(AssertionError):
                self._inode(kwargs.pop('st_mode'), **kwargs)

    def test_chunk_clone(self):
        clone = Clone(inode_id=InodeIDMap().next('a'), offset=17, length=3)
        self.assertEqual('a:17+3', repr(clone))
        self.assertEqual('a:17+3@22', repr(ChunkClone(offset=22, clone=clone)))

    def test_chunk(self):
        id_map = InodeIDMap()
        chunk = Chunk(kind=Extent.Kind.DATA, length=12, chunk_clones=set())
        self.assertEqual('(DATA/12)', repr(chunk))
        ino_id = id_map.next('a')
        chunk.chunk_clones.add(ChunkClone(
            offset=3, clone=Clone(inode_id=ino_id, offset=7, length=2),
        ))
        self.assertEqual('(DATA/12: a:7+2@3)', repr(chunk))
        chunk.chunk_clones.add(ChunkClone(
            offset=4, clone=Clone(inode_id=ino_id, offset=5, length=6),
        ))
        self.assertIn(
            repr(chunk),  # The set can be in one of two orders
            ('(DATA/12: a:7+2@3, a:5+6@4)', '(DATA/12: a:5+6@4, a:7+2@3)'),
        )


if __name__ == '__main__':
    unittest.main()
