#!/usr/bin/env python3
import unittest

from ..parse_dump import SendStreamItems
from ..subvolume_set import SubvolumeSet, SubvolumeSetMutator


class SubvolumeSetTestCase(unittest.TestCase):
    '''
    This does not test applying `SendStreamItems` from `Subvolume` or
    `IncompleteInode` becasuse those classes have their own tests.
    '''

    def test_subvolume_set(self):
        si = SendStreamItems
        subvols = SubvolumeSet.new()

        # Make a tiny subvolume
        cat_mutator = SubvolumeSetMutator.new(subvols, si.subvol(
            path=b'cat', uuid='abe', transid=3,
        ))
        cat_mutator.apply_item(si.mkfile(path=b'from'))
        cat_mutator.apply_item(si.write(path=b'from', offset=0, data='hi'))
        cat_mutator.apply_item(si.mkfile(path=b'to'))
        bad_clone = si.clone(
            path=b'to', offset=0, from_uuid='BAD', from_transid=3,
            from_path=b'from', clone_offset=0, len=2,
        )
        with self.assertRaisesRegex(RuntimeError, 'Unknown from_uuid '):
            cat_mutator.apply_item(bad_clone)
        cat_mutator.apply_item(bad_clone._replace(from_uuid='abe'))
        cat = cat_mutator.subvolume
        self.assertEqual('cat', repr(cat.id_map.description))
        self.assertEqual('cat', repr(cat.id_map.description))

        # Make a snapshot
        tiger = SubvolumeSetMutator.new(subvols, si.snapshot(
            path=b'tiger',
            uuid='ee', transid=7,
            parent_uuid='abe', parent_transid=3,
        )).subvolume
        self.assertEqual('cat', repr(cat.id_map.description))
        self.assertEqual('tiger', repr(tiger.id_map.description))

        # Get `repr` to show some disambiguation
        cat2 = SubvolumeSetMutator.new(subvols, si.subvol(
            path=b'cat', uuid='app', transid=3,
        )).subvolume
        self.assertEqual('cat@ab', repr(cat.id_map.description))
        self.assertEqual('cat@ap', repr(cat2.id_map.description))

        # Now create an ambiguous repr.
        tiger2 = SubvolumeSetMutator.new(subvols, si.subvol(
            path=b'tiger', uuid='eep', transid=3,
        )).subvolume
        self.assertEqual('tiger@ee-ERROR', repr(tiger.id_map.description))
        self.assertEqual('tiger@eep', repr(tiger2.id_map.description))

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
