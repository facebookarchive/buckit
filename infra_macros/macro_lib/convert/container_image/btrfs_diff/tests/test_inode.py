#!/usr/bin/env python3
import unittest

from ..extent import Extent
from ..inode import Chunk, ChunkClone, Clone, Inode, IncompleteInode
from ..inode_id import InodeIDMap


class InodeTestCase(unittest.TestCase):

    def test_incomplete_inode(self):
        self.assertEqual('(IncompleteInode: a,b/17)', repr(IncompleteInode(
            id=InodeIDMap().next(['a', 'b']),
            extent=Extent.empty().truncate(length=17),
        )))

    def test_inode(self):
        self.assertEqual('(Inode: c)', repr(Inode(
            id=InodeIDMap().next(['c']), chunks=(),
        )))

    def test_chunk_clone(self):
        clone = Clone(inode_id=InodeIDMap().next(['a']), offset=17, length=3)
        self.assertEqual('a:17+3', repr(clone))
        self.assertEqual('a:17+3@22', repr(ChunkClone(offset=22, clone=clone)))

    def test_chunk(self):
        id_map = InodeIDMap()
        chunk = Chunk(kind=Extent.Kind.DATA, length=12, chunk_clones=set())
        self.assertEqual('(DATA/12)', repr(chunk))
        ino_id = id_map.next(['a'])
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
