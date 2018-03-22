#!/usr/bin/env python3
import unittest

from ..inode_id import InodeID, InodeIDMap


class InodeIDTestCase(unittest.TestCase):

    def test_inode_id_and_map(self):
        id_map = InodeIDMap()

        # Check the root inode
        ino_root = id_map.get_id(b'.')
        self.assertEqual({b'.'}, id_map.get_paths(ino_root))
        self.assertEqual('.', repr(ino_root))
        self.assertEqual(set(), id_map.get_children(ino_root))

        # Make a new ID with a path
        ino_a = id_map.next(b'./a/')
        self.assertEqual(1, ino_a.id)
        self.assertIs(id_map, ino_a.id_map)
        self.assertEqual('a', repr(ino_a))
        self.assertEqual({b'a'}, id_map.get_children(ino_root))
        self.assertEqual(set(), id_map.get_children(ino_a))

        # Anonymous inode, then add multiple paths
        ino_b = id_map.next()  # initially anonymous
        self.assertEqual(2, ino_b.id)
        self.assertIs(id_map, ino_b.id_map)
        self.assertEqual('ANON_INODE#2', repr(ino_b))
        id_map.add_path(ino_b, b'a/d')
        self.assertEqual({b'a/d'}, id_map.get_children(ino_a))
        self.assertEqual({b'a/d'}, id_map.get_paths(ino_b))
        id_map.add_path(ino_b, b'a/c')
        self.assertEqual({b'a/c', b'a/d'}, id_map.get_children(ino_a))
        self.assertEqual({b'a/c', b'a/d'}, id_map.get_paths(ino_b))
        self.assertEqual('a/c,a/d', repr(ino_b))
        self.assertIs(ino_b, id_map.remove_path(b'a/c'))
        self.assertEqual({b'a/d'}, id_map.get_children(ino_a))
        self.assertEqual({b'a/d'}, id_map.get_paths(ino_b))
        self.assertEqual('a/d', repr(ino_b))

        self.assertEqual({b'a'}, id_map.get_children(ino_root))

        # Look-up by ID
        self.assertIs(ino_a, id_map.get_id(b'a'))
        self.assertIs(ino_b, id_map.get_id(b'a/d'))

        # Cannot remove non-empty directories
        with self.assertRaisesRegex(RuntimeError, "remove b'a'.*has children"):
            id_map.remove_path(b'a')

        # Check that we clean up empty path sets
        self.assertIn(ino_b.id, id_map.id_to_paths)
        self.assertIs(ino_b, id_map.remove_path(b'a/d'))
        self.assertNotIn(ino_b.id, id_map.id_to_paths)

        # Catch str/byte mixups
        with self.assertRaises(TypeError):
            id_map.get_id('a')
        with self.assertRaises(TypeError):
            id_map.remove_path('a')
        with self.assertRaises(TypeError):
            id_map.add_path('b')

        # Other errors
        with self.assertRaisesRegex(RuntimeError, 'Wrong map for InodeID #17'):
            id_map.get_paths(InodeID(id=17, id_map=InodeIDMap()))
        with self.assertRaisesRegex(
            RuntimeError, "Path b'a' has 2 inodes: 3 and 1"
        ):
            id_map.next(b'a')
        with self.assertRaisesRegex(RuntimeError, "Need relative path"):
            id_map.add_path(ino_b, b'/a/e')
        with self.assertRaisesRegex(RuntimeError, "parent does not exist"):
            id_map.add_path(ino_b, b'b/c')

        # OK to remove since it's now empty
        id_map.remove_path(b'a')


if __name__ == '__main__':
    unittest.main()
