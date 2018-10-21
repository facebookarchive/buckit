#!/usr/bin/env python3
import unittest

from ..dep_graph import (
    DependencyGraph, gen_dependency_order_items, ItemProv, ItemReq,
    ItemReqsProvs, ValidatedReqsProvs,
)
from ..items import (
    CopyFileItem, FilesystemRootItem, ImageItem, MakeDirsItem,
    MultiRpmAction, PhaseOrder, RpmActionType,
)
from ..provides import ProvidesDirectory, ProvidesFile
from ..requires import require_directory


PATH_TO_ITEM = {
    '/': FilesystemRootItem(from_target=''),
    '/a/b/c': MakeDirsItem(from_target='', into_dir='/', path_to_make='a/b/c'),
    '/a/d/e': MakeDirsItem(from_target='', into_dir='a', path_to_make='d/e'),
    '/a/b/c/F': CopyFileItem(from_target='', source='x', dest='a/b/c/F'),
    '/a/d/e/G': CopyFileItem(from_target='', source='G', dest='a/d/e/'),
}


class ValidateReqsProvsTestCase(unittest.TestCase):

    def test_duplicate_paths_in_same_item(self):

        class BadDuplicatePathItem(metaclass=ImageItem):
            def requires(self):
                yield require_directory('a')

            def provides(self):
                yield ProvidesDirectory(path='a')

        with self.assertRaisesRegex(AssertionError, '^Same path in '):
            ValidatedReqsProvs([BadDuplicatePathItem(from_target='t')])

    def test_duplicate_paths_provided(self):
        with self.assertRaisesRegex(
            RuntimeError, '^Both .* and .* from .* provide the same path$'
        ):
            ValidatedReqsProvs([
                CopyFileItem(from_target='', source='x', dest='y/'),
                MakeDirsItem(from_target='', into_dir='/', path_to_make='y/x'),
            ])

    def test_unmatched_requirement(self):
        item = CopyFileItem(from_target='', source='x', dest='y')
        with self.assertRaises(
            RuntimeError,
            msg='^At /: nothing in set() matches the requirement '
                f'{ItemReq(requires=require_directory("/"), item=item)}$',
        ):
            ValidatedReqsProvs([item])

    def test_paths_to_reqs_provs(self):
        self.assertEqual(
            ValidatedReqsProvs(PATH_TO_ITEM.values()).path_to_reqs_provs,
            {
                '/': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesDirectory(path='/'), PATH_TO_ITEM['/']
                    )},
                    item_reqs={ItemReq(
                        require_directory('/'), PATH_TO_ITEM['/a/b/c']
                    )}
                ),
                '/a': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesDirectory(path='a'), PATH_TO_ITEM['/a/b/c']
                    )},
                    item_reqs={ItemReq(
                        require_directory('a'), PATH_TO_ITEM['/a/d/e']
                    )},
                ),
                '/a/b': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesDirectory(path='a/b'), PATH_TO_ITEM['/a/b/c']
                    )},
                    item_reqs=set(),
                ),
                '/a/b/c': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesDirectory(path='a/b/c'), PATH_TO_ITEM['/a/b/c']
                    )},
                    item_reqs={ItemReq(
                        require_directory('a/b/c'), PATH_TO_ITEM['/a/b/c/F']
                    )},
                ),
                '/a/b/c/F': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesFile(path='a/b/c/F'), PATH_TO_ITEM['/a/b/c/F']
                    )},
                    item_reqs=set(),
                ),
                '/a/d': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesDirectory(path='a/d'), PATH_TO_ITEM['/a/d/e']
                    )},
                    item_reqs=set(),
                ),
                '/a/d/e': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesDirectory(path='a/d/e'), PATH_TO_ITEM['/a/d/e']
                    )},
                    item_reqs={ItemReq(
                        require_directory('a/d/e'), PATH_TO_ITEM['/a/d/e/G']
                    )},
                ),
                '/a/d/e/G': ItemReqsProvs(
                    item_provs={ItemProv(
                        ProvidesFile(path='a/d/e/G'), PATH_TO_ITEM['/a/d/e/G']
                    )},
                    item_reqs=set(),
                ),
            }
        )


class DependencyGraphTestCase(unittest.TestCase):

    def test_dependency_graph(self):
        dg = DependencyGraph(PATH_TO_ITEM.values())
        self.assertEquals(dg.item_to_predecessors, {
            PATH_TO_ITEM[k]: {PATH_TO_ITEM[v] for v in vs} for k, vs in {
                '/a/b/c': {'/'},
                '/a/d/e': {'/a/b/c'},
                '/a/b/c/F': {'/a/b/c'},
                '/a/d/e/G': {'/a/d/e'},
            }.items()
        })
        self.assertEquals(dg.predecessor_to_items, {
            PATH_TO_ITEM[k]: {PATH_TO_ITEM[v] for v in vs} for k, vs in {
                '/': {'/a/b/c'},
                '/a/b/c': {'/a/d/e', '/a/b/c/F'},
                '/a/b/c/F': set(),
                '/a/d/e': {'/a/d/e/G'},
                '/a/d/e/G': set(),
            }.items()
        })
        self.assertEquals(dg.items_without_predecessors, {PATH_TO_ITEM['/']})


class DependencyOrderItemsTestCase(unittest.TestCase):

    def test_gen_dependency_order_items(self):
        self.assertIn(
            tuple(gen_dependency_order_items(PATH_TO_ITEM.values())),
            {
                tuple(PATH_TO_ITEM[p] for p in paths) for paths in [
                    # A few orders are valid, don't make the test fragile.
                    ['/', '/a/b/c', '/a/b/c/F', '/a/d/e', '/a/d/e/G'],
                    ['/', '/a/b/c', '/a/d/e', '/a/b/c/F', '/a/d/e/G'],
                    ['/', '/a/b/c', '/a/d/e', '/a/d/e/G', '/a/b/c/F'],
                ]
            },
        )

    def test_cycle_detection(self):

        def requires_provides_directory_class(requires_dir, provides_dir):

            class RequiresProvidesDirectory(metaclass=ImageItem):
                def requires(self):
                    yield require_directory(requires_dir)

                def provides(self):
                    yield ProvidesDirectory(path=provides_dir)

            return RequiresProvidesDirectory

        # Everything works without a cycle
        first = FilesystemRootItem(from_target='')
        second = requires_provides_directory_class('/', 'a')(from_target='')
        third = MakeDirsItem(from_target='', into_dir='a', path_to_make='b/c')
        self.assertEqual(
            [first, second, third],
            list(gen_dependency_order_items([second, first, third])),
        )

        # Let's change `second` to get a cycle
        with self.assertRaisesRegex(AssertionError, '^Cycle in '):
            list(gen_dependency_order_items([
                requires_provides_directory_class('a/b', 'a')(from_target=''),
                first, third,
            ]))

    def test_phase_order(self):

        class FakeFileRemove:
            def __init__(self):
                self.phase_order = PhaseOrder.FILE_REMOVE

        first = FilesystemRootItem(from_target='')
        second = FakeFileRemove()
        third = MakeDirsItem(from_target='', into_dir='/', path_to_make='a/b')
        self.assertEqual(
            [first, second, third],
            list(gen_dependency_order_items([second, first, third])),
        )

    def test_rpm_action_conflict_detection(self):
        install = MultiRpmAction.new(
            action=RpmActionType.install,
            rpms={'cat', 'dog'},
            yum_from_snapshot='/fake/yum',
        )
        remove = MultiRpmAction.new(
            action=RpmActionType.remove_if_exists,
            rpms={'sheep', 'dog'},
            yum_from_snapshot='/fake/yum',
        )
        with self.assertRaisesRegex(RuntimeError, 'RPM action conflict for d'):
            list(gen_dependency_order_items([install, remove]))


if __name__ == '__main__':
    unittest.main()
