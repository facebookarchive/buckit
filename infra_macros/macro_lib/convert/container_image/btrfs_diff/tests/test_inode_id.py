#!/usr/bin/env python3
import copy
import unittest

from types import SimpleNamespace

from ..inode_id import InodeID, InodeIDMap

from .deepcopy_test import DeepCopyTestCase


class InodeIDTestCase(DeepCopyTestCase):

    def _check_id_and_map(self):
        '''
        The `yield` statements in this generator allow `DeepCopyTestCase`
        to replace `ns.id_map` with a different object (either a `deepcopy`
        or a pre-`deepcopy` original from a prior run). See the docblock of
        `DeepCopyTestCase` for the details.
        '''
        INO1_ID = 1
        INO2_ID = 2
        STEP_MADE_ANON_INODE = 'made anon inode'  # has special 'replace' logic

        # Shared scope between the outer function and `maybe_replace_map`
        ns = SimpleNamespace()

        def maybe_replace_map(id_map, step_name):
            new_map = yield step_name, id_map
            if new_map is not id_map:
                # If the map was replaced, we must fix up the inode objects.
                if hasattr(ns, 'ino1'):
                    ns.ino1 = new_map.get_id(b'a')
                if hasattr(ns, 'ino2'):
                    if step_name == STEP_MADE_ANON_INODE:
                        ns.ino2 = InodeID(id=2, id_map=new_map)
                    else:
                        # we add a/c later, remove a/c earlier, this is enough
                        ns.ino2 = new_map.get_id(b'a/d')
            return new_map  # noqa: B901

        id_map = yield from maybe_replace_map(InodeIDMap(), 'empty')

        # Check the root inode
        ino_root = id_map.get_id(b'.')
        self.assertEqual({b'.'}, id_map.get_paths(ino_root))
        self.assertEqual('.', repr(ino_root))
        self.assertEqual(set(), id_map.get_children(ino_root))

        # Make a new ID with a path
        ns.ino1 = id_map.next(b'./a/')
        id_map = yield from maybe_replace_map(id_map, 'made a')
        self.assertEqual(INO1_ID, ns.ino1.id)
        self.assertIs(id_map, ns.ino1.id_map)
        self.assertEqual('a', repr(ns.ino1))
        self.assertEqual({b'a'}, id_map.get_children(ino_root))
        self.assertEqual(set(), id_map.get_children(ns.ino1))

        # Anonymous inode, then add multiple paths
        ns.ino2 = id_map.next()  # initially anonymous
        id_map = yield from maybe_replace_map(id_map, STEP_MADE_ANON_INODE)
        self.assertEqual(INO2_ID, ns.ino2.id)
        self.assertIs(id_map, ns.ino2.id_map)
        self.assertEqual('ANON_INODE#2', repr(ns.ino2))
        id_map.add_path(ns.ino2, b'a/d')
        id_map = yield from maybe_replace_map(id_map, 'added a/d name')
        self.assertEqual({b'a/d'}, id_map.get_children(ns.ino1))
        self.assertEqual({b'a/d'}, id_map.get_paths(ns.ino2))
        id_map.add_path(ns.ino2, b'a/c')
        id_map = yield from maybe_replace_map(id_map, 'added a/c name')
        self.assertEqual({b'a/c', b'a/d'}, id_map.get_children(ns.ino1))
        self.assertEqual({b'a/c', b'a/d'}, id_map.get_paths(ns.ino2))
        self.assertEqual('a/c,a/d', repr(ns.ino2))
        self.assertIs(ns.ino2, id_map.remove_path(b'a/c'))
        id_map = yield from maybe_replace_map(id_map, 'removed a/c name')
        self.assertEqual({b'a/d'}, id_map.get_children(ns.ino1))
        self.assertEqual({b'a/d'}, id_map.get_paths(ns.ino2))
        self.assertEqual('a/d', repr(ns.ino2))

        self.assertEqual({b'a'}, id_map.get_children(ino_root))

        # Look-up by ID
        self.assertIs(ns.ino1, id_map.get_id(b'a'))
        self.assertIs(ns.ino2, id_map.get_id(b'a/d'))

        # Cannot remove non-empty directories
        with self.assertRaisesRegex(RuntimeError, "remove b'a'.*has children"):
            id_map.remove_path(b'a')

        # Check that we clean up empty path sets
        self.assertIn(ns.ino2.id, id_map.id_to_paths)
        self.assertIs(ns.ino2, id_map.remove_path(b'a/d'))
        id_map = yield from maybe_replace_map(id_map, 'removed a/d name')
        self.assertNotIn(INO2_ID, id_map.id_to_paths)

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
            id_map.add_path(ns.ino2, b'/a/e')
        with self.assertRaisesRegex(RuntimeError, "parent does not exist"):
            id_map.add_path(ns.ino2, b'b/c')

        # OK to remove since it's now empty
        id_map.remove_path(b'a')
        id_map = yield from maybe_replace_map(id_map, 'removed a')
        self.assertEqual({0: {b'.'}}, id_map.id_to_paths)
        self.assertEqual([b'.'], list(id_map.path_to_id.keys()))
        self.assertEqual(
            InodeID(id=0, id_map=id_map), id_map.path_to_id[b'.'],
        )
        self.assertEqual(0, len(id_map.id_to_children))

    def test_inode_id_and_map(self):
        self.check_deepcopy_at_each_step(self._check_id_and_map)

    def test_description(self):
        cat_map = InodeIDMap(description='cat')
        self.assertEqual('cat@food', repr(cat_map.next(b'food')))


if __name__ == '__main__':
    unittest.main()
