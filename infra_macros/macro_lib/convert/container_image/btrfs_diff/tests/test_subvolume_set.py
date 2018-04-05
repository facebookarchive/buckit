#!/usr/bin/env python3
import unittest

from ..freeze import freeze
from ..parse_dump import SendStreamItems
from ..subvolume_set import SubvolumeSet, SubvolumeSetMutator

from .subvolume_utils import (
    serialize_frozen_subvolume_set, serialized_subvolume_set_add_fake_inode_ids
)


class SubvolumeSetTestCase(unittest.TestCase):
    '''
    This does not test applying `SendStreamItems` from `Subvolume` or
    `IncompleteInode` becasuse those classes have their own tests.
    '''

    def setUp(self):
        # Print more data to simplify debugging
        self.maxDiff = 10e4
        unittest.util._MAX_LENGTH = 10e4

    def _check_repr(self, expected, subvol_set: SubvolumeSet):
        self.assertEqual(
            serialized_subvolume_set_add_fake_inode_ids(expected),
            serialize_frozen_subvolume_set(subvol_set),
        )

    def test_subvolume_set(self):
        si = SendStreamItems
        subvols = SubvolumeSet.new()
        # We'll check that freezing the SubvolumeSet at various points
        # results in an object that is not affected by future mutations.
        reprs_and_frozens = []

        # Make a tiny subvolume
        cat_mutator = SubvolumeSetMutator.new(subvols, si.subvol(
            path=b'cat', uuid='abe', transid=3,
        ))
        cat_mutator.apply_item(si.mkfile(path=b'from'))
        cat_mutator.apply_item(si.write(path=b'from', offset=0, data='hi'))
        cat_mutator.apply_item(si.mkfile(path=b'to'))
        cat_mutator.apply_item(si.mkfile(path=b'hole'))
        cat_mutator.apply_item(si.truncate(path=b'hole', size=5))
        bad_clone = si.clone(
            path=b'to', offset=0, from_uuid='BAD', from_transid=3,
            from_path=b'from', clone_offset=0, len=2,
        )
        with self.assertRaisesRegex(RuntimeError, 'Unknown from_uuid '):
            cat_mutator.apply_item(bad_clone)
        cat_mutator.apply_item(bad_clone._replace(from_uuid='abe'))
        cat = cat_mutator.subvolume
        self.assertEqual('cat', repr(cat.id_map.inner.description))
        self.assertEqual('cat', repr(cat.id_map.inner.description))

        reprs_and_frozens.append(({
            'cat': ('(Dir)', {
                'from': '(File d2(cat@to:0+2@0))',
                'to': '(File d2(cat@from:0+2@0))',
                'hole': '(File h5)',
            }),
        }, freeze(subvols)))
        self._check_repr(*reprs_and_frozens[-1])

        # `tiger` is a snapshot of `cat`
        tiger_mutator = SubvolumeSetMutator.new(subvols, si.snapshot(
            path=b'tiger',
            uuid='ee', transid=7,
            parent_uuid='abe', parent_transid=3,  # Use the UUID of `cat`
        ))
        tiger = tiger_mutator.subvolume

        self.assertIs(
            subvols.name_uuid_prefix_counts,
            tiger.id_map.inner.description.name_uuid_prefix_counts,
        )
        self.assertEqual('cat', repr(cat.id_map.inner.description))
        self.assertEqual('tiger', repr(tiger.id_map.inner.description))

        tiger_mutator.apply_item(si.unlink(path=b'from'))
        tiger_mutator.apply_item(si.unlink(path=b'hole'))
        reprs_and_frozens.append(({
            'cat': ('(Dir)', {
                'from': '(File d2(cat@to:0+2@0/tiger@to:0+2@0))',
                'to': '(File d2(cat@from:0+2@0/tiger@to:0+2@0))',
                'hole': '(File h5)',
            }),
            'tiger': ('(Dir)', {
                'to': '(File d2(cat@from:0+2@0/cat@to:0+2@0))',
            }),
        }, freeze(subvols)))
        self._check_repr(*reprs_and_frozens[-1])

        # Clone some data from `cat@hole` into `tiger@to`.
        tiger_mutator.apply_item(si.clone(
            path=b'to', offset=1, len=2, from_uuid='abe', from_transid=3,
            from_path=b'hole', clone_offset=2,
        ))
        # Note that the tiger@to references shrink to 1 bytes.
        reprs_and_frozens.append(({
            'cat': ('(Dir)', {
                'from': '(File d2(cat@to:0+2@0/tiger@to:0+1@0))',
                'to': '(File d2(cat@from:0+2@0/tiger@to:0+1@0))',
                'hole': '(File h5(tiger@to:1+2@2))',
            }),
            'tiger': ('(Dir)', {
                'to': '(File d1(cat@from:0+1@0/cat@to:0+1@0)'
                      'h2(cat@hole:2+2@0))',
            }),
        }, freeze(subvols)))
        self._check_repr(*reprs_and_frozens[-1])

        # Get `repr` to show some disambiguation
        cat2 = SubvolumeSetMutator.new(subvols, si.subvol(
            path=b'cat', uuid='app', transid=3,
        )).subvolume
        self.assertEqual('cat@ab', repr(cat.id_map.inner.description))
        self.assertEqual('cat@ap', repr(cat2.id_map.inner.description))
        reprs_and_frozens.append(({
            'cat@ap': '(Dir)',
            # Difference from the previous: `s/cat/cat@ab/`
            'cat@ab': ('(Dir)', {
                'from': '(File d2(cat@ab@to:0+2@0/tiger@to:0+1@0))',
                'to': '(File d2(cat@ab@from:0+2@0/tiger@to:0+1@0))',
                'hole': '(File h5(tiger@to:1+2@2))',
            }),
            'tiger': ('(Dir)', {
                'to': '(File d1(cat@ab@from:0+1@0/cat@ab@to:0+1@0)'
                      'h2(cat@ab@hole:2+2@0))',
            }),
        }, freeze(subvols)))

        # Now create an ambiguous repr.
        tiger2 = SubvolumeSetMutator.new(subvols, si.subvol(
            path=b'tiger', uuid='eep', transid=3,
        )).subvolume
        self.assertEqual(
            'tiger@ee-ERROR', repr(tiger.id_map.inner.description),
        )
        self.assertEqual('tiger@eep', repr(tiger2.id_map.inner.description))

        # This ensures that the frozen SubvolumeSets did not get changed
        # by mutations on the original.
        for expected, frozen in reprs_and_frozens:
            self._check_repr(expected, frozen)

    def test_errors(self):
        si = SendStreamItems
        subvols = SubvolumeSet.new()

        with self.assertRaisesRegex(RuntimeError, 'must specify subvolume'):
            SubvolumeSetMutator.new(subvols, si.mkfile(path=b'foo'))

        with self.assertRaisesRegex(KeyError, 'lala-uuid-foo'):
            SubvolumeSetMutator.new(subvols, si.snapshot(
                path=b'x',
                uuid='y', transid=5,
                parent_uuid='lala-uuid-foo', parent_transid=3,
            ))

        def insert_cat(transid):
            SubvolumeSetMutator.new(subvols, si.subvol(
                path=b'cat', uuid='a', transid=transid,
            ))

        insert_cat(3)
        with self.assertRaisesRegex(RuntimeError, ' is already in use: '):
            insert_cat(555)


if __name__ == '__main__':
    unittest.main()
