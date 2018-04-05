#!/usr/bin/env python3
import copy
import unittest

from types import SimpleNamespace

from ..freeze import freeze
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
        # Stores inode objects pointing at the un-frozen (mutable) `id_map`.
        mut_ns = SimpleNamespace()

        def maybe_replace_map(id_map, step_name):
            new_map = yield step_name, id_map
            if new_map is not id_map:
                # If the map was replaced, we must fix up our inode objects.
                mut_ns.ino_root = new_map.get_id(b'.')
                if hasattr(mut_ns, 'ino1'):
                    mut_ns.ino1 = new_map.get_id(b'a')
                if hasattr(mut_ns, 'ino2'):
                    if step_name == STEP_MADE_ANON_INODE:
                        mut_ns.ino2 = InodeID(id=2, inner_id_map=new_map.inner)
                    else:
                        # we add a/c later, remove a/c earlier, this is enough
                        mut_ns.ino2 = new_map.get_id(b'a/d')
            return new_map  # noqa: B901

        def unfrozen_and_frozen_impl(id_map, mut_ns):
            'Run all checks on the mutable map and on its frozen counterpart'
            yield id_map, mut_ns
            frozen_map = freeze(id_map)
            yield frozen_map, SimpleNamespace(**{
                # Avoiding `frozen_map.get_id(...id_map.get_paths(v))`
                # since that won't work with an anonymous inode.
                k: InodeID(id=v.id, inner_id_map=frozen_map.inner)
                    for k, v in mut_ns.__dict__.items()
                        if v is not None  # for `mut_ns.ino2 = new_map.get_id`
            })

        def unfrozen_and_frozen(id_map, mut_ns):
            res = list(unfrozen_and_frozen_impl(id_map, mut_ns))
            # The whole test would be useless if the generator didn't return
            # any items, so add some paranoia around that.
            self.assertEqual(2, len(res), repr(res))
            return res

        id_map = yield from maybe_replace_map(InodeIDMap.new(), 'empty')

        # Check the root inode
        mut_ns.ino_root = id_map.get_id(b'.')
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual('.', repr(ns.ino_root))
            self.assertEqual({b'.'}, im.get_paths(ns.ino_root))
            self.assertEqual(set(), im.get_children(ns.ino_root))

        # Make a new ID with a path
        mut_ns.ino1 = id_map.next(b'./a/')
        id_map = yield from maybe_replace_map(id_map, 'made a')
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual(INO1_ID, ns.ino1.id)
            self.assertIs(im.inner, ns.ino1.inner_id_map)
            self.assertEqual('a', repr(ns.ino1))
            self.assertEqual({b'a'}, im.get_children(ns.ino_root))
            self.assertEqual(set(), im.get_children(ns.ino1))

        # Anonymous inode, then add multiple paths
        mut_ns.ino2 = id_map.next()  # initially anonymous
        id_map = yield from maybe_replace_map(id_map, STEP_MADE_ANON_INODE)
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual(INO2_ID, ns.ino2.id)
            self.assertIs(im.inner, ns.ino2.inner_id_map)
            self.assertEqual('ANON_INODE#2', repr(ns.ino2))
        id_map.add_path(mut_ns.ino2, b'a/d')
        id_map = yield from maybe_replace_map(id_map, 'added a/d name')
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual({b'a/d'}, im.get_children(ns.ino1))
            self.assertEqual({b'a/d'}, im.get_paths(ns.ino2))
        id_map.add_path(mut_ns.ino2, b'a/c')
        id_map = yield from maybe_replace_map(id_map, 'added a/c name')
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual({b'a/c', b'a/d'}, im.get_children(ns.ino1))
            self.assertEqual({b'a/c', b'a/d'}, im.get_paths(ns.ino2))
            self.assertEqual('a/c,a/d', repr(ns.ino2))
        # Try removing from the frozen map before changing the original one.
        with self.assertRaisesRegex(AttributeError, "mappingproxy.* no .*pop"):
            freeze(id_map).remove_path(b'a/c')
        self.assertIs(mut_ns.ino2, id_map.remove_path(b'a/c'))
        saved_frozen_map = freeze(id_map)  # We'll check this later
        id_map = yield from maybe_replace_map(id_map, 'removed a/c name')
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual({b'a/d'}, im.get_children(ns.ino1))
            self.assertEqual({b'a/d'}, im.get_paths(ns.ino2))
            self.assertEqual('a/d', repr(ns.ino2))

            self.assertEqual({b'a'}, im.get_children(ns.ino_root))

        # Look-up by ID
        for (im, ns), check_same in zip(
            unfrozen_and_frozen(id_map, mut_ns),
            # `is` comparison would be harder to implement for the frozen
            # variant, and meaningless because we just constructed it.
            [self.assertIs, self.assertEqual],
        ):
            check_same(ns.ino1, im.get_id(b'a'))
            check_same(ns.ino2, im.get_id(b'a/d'))

        # Cannot remove non-empty directories
        with self.assertRaisesRegex(RuntimeError, "remove b'a'.*has children"):
            id_map.remove_path(b'a')

        # Check that we clean up empty path sets
        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertIn(ns.ino2.id, im.inner.id_to_paths)
        self.assertIs(mut_ns.ino2, id_map.remove_path(b'a/d'))
        id_map = yield from maybe_replace_map(id_map, 'removed a/d name')
        for im, _ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertNotIn(INO2_ID, im.inner.id_to_paths)

        for im, ns in unfrozen_and_frozen(id_map, mut_ns):
            # Catch str/byte mixups
            with self.assertRaises(TypeError):
                im.get_id('a')
            with self.assertRaises(TypeError):
                im.remove_path('a')
            with self.assertRaises(TypeError):
                im.add_path('b')

            # Other errors
            with self.assertRaisesRegex(RuntimeError, 'Wrong map for .* #17'):
                im.get_paths(
                    InodeID(id=17, inner_id_map=InodeIDMap.new().inner)
                )
            with self.assertRaisesRegex(RuntimeError, "Need relative path"):
                im.add_path(ns.ino1, b'/a/e')
            with self.assertRaisesRegex(RuntimeError, "parent does not exist"):
                im.add_path(ns.ino1, b'b/c')

        # This error differs between unfrozen & frozen:
        with self.assertRaisesRegex(
            RuntimeError, "Path b'a' has 2 inodes: 3 and 1",
        ):
            id_map.next(b'a')
        with self.assertRaisesRegex(
            TypeError, "'NoneType' object is not an iterator",
        ):
            freeze(id_map).next(b'a')

        # OK to remove since it's now empty
        id_map.remove_path(b'a')
        id_map = yield from maybe_replace_map(id_map, 'removed a')
        for im, _ns in unfrozen_and_frozen(id_map, mut_ns):
            self.assertEqual({0: {b'.'}}, im.inner.id_to_paths)
            self.assertEqual([b'.'], list(im.path_to_id.keys()))
            self.assertEqual(
                InodeID(id=0, inner_id_map=im.inner), im.path_to_id[b'.'],
            )
            self.assertEqual(0, len(im.id_to_children))

        # Even though we changed `id_map` a lot, `saved_frozen` is still
        # in the same state where we took the snapshot.
        self.assertIsNone(saved_frozen_map.inode_id_counter)
        self.assertEqual({
            b'.': InodeID(id=0, inner_id_map=saved_frozen_map.inner),
            b'a': InodeID(id=INO1_ID, inner_id_map=saved_frozen_map.inner),
            b'a/d': InodeID(id=INO2_ID, inner_id_map=saved_frozen_map.inner),
        }, saved_frozen_map.path_to_id)
        self.assertEqual('', saved_frozen_map.inner.description)
        self.assertEqual(
            {0: {b'.'}, INO1_ID: {b'a'}, INO2_ID: {b'a/d'}},
            saved_frozen_map.inner.id_to_paths,
        )
        self.assertEqual(
            {0: {b'a'}, INO1_ID: {b'a/d'}},
            saved_frozen_map.id_to_children,
        )

    def test_inode_id_and_map(self):
        self.check_deepcopy_at_each_step(self._check_id_and_map)

    def test_description(self):
        cat_map = InodeIDMap.new(description='cat')
        self.assertEqual('cat@food', repr(cat_map.next(b'food')))

    def test_hashing_and_equality(self):
        maps = [InodeIDMap.new() for i in range(100)]
        hashes = {hash(m.get_id(b'.')) for m in maps}
        self.assertNotEqual({next(iter(hashes))}, hashes)
        # Even 5 collisions out of 100 is too many, but the goal is to avoid
        # flaky tests at all costs.
        self.assertGreater(len(hashes), 95)

        id1 = InodeIDMap.new().get_id(b'.')
        id2 = InodeID(id=0, inner_id_map=id1.inner_id_map)
        self.assertEqual(id1, id2)
        self.assertEqual(hash(id1), hash(id2))


if __name__ == '__main__':
    unittest.main()
