#!/usr/bin/env python3
import unittest

from ..inode_id import InodeID, InodeIDMap


class InodeIDTestCase(unittest.TestCase):

    def test_inode_id_and_map(self):
        id_map = InodeIDMap()

        # Making a new ID, and `str` paths
        ino_a = id_map.next(['a/b'])
        self.assertEqual(0, ino_a.id)
        self.assertIs(id_map, ino_a.id_map)
        self.assertEqual('a/b', repr(ino_a))

        # Anonymous inode, adding multiple `byte` paths
        ino_b = id_map.next([])  # initially anonymous
        self.assertEqual(1, ino_b.id)
        self.assertIs(id_map, ino_b.id_map)
        self.assertEqual('ANON_INODE#1', repr(ino_b))
        id_map.add_paths(ino_b, ['a/d', 'a/c'])
        self.assertEqual('a/c,a/d', repr(ino_b))

        # Look-up by ID
        self.assertIs(ino_a, id_map.get_id('a/b'))
        self.assertIs(ino_b, id_map.get_id('a/d'))

        # Errors
        with self.assertRaisesRegex(RuntimeError, 'Wrong map for InodeID #17'):
            id_map.get_paths(InodeID(id=17, id_map=InodeIDMap()))
        with self.assertRaisesRegex(
            RuntimeError, 'Path a/b has 2 inodes: 2 and 0'
        ):
            id_map.next(['a/b'])


if __name__ == '__main__':
    unittest.main()
