#!/usr/bin/env python3
import unittest

from ..parse_dump import SendStreamItems
from ..subvolume_set import SubvolumeSet


class SubvolumeSetTestCase(unittest.TestCase):
    '''
    This does not test applying `SendStreamItems` from `Subvolume` or
    `IncompleteInode` becasuse those classes have their own tests.
    '''

    def test_subvolume_set(self):
        si = SendStreamItems
        subvols = SubvolumeSet.new()

        # Make a tiny subvolume
        cat = subvols.apply_first_sendstream_item(si.subvol(
            path=b'cat', uuid='abe', transid=3,
        ))
        self.assertEqual('cat', repr(cat.id_map.description))

        # Make a snapshot
        tiger = subvols.apply_first_sendstream_item(si.snapshot(
            path=b'tiger',
            uuid='ee', transid=7,
            parent_uuid='abe', parent_transid=3,
        ))
        self.assertEqual('cat', repr(cat.id_map.description))
        self.assertEqual('tiger', repr(tiger.id_map.description))

        # Get `repr` to show some disambiguation
        cat2 = subvols.apply_first_sendstream_item(si.subvol(
            path=b'cat', uuid='app', transid=3,
        ))
        self.assertEqual('cat@ab', repr(cat.id_map.description))
        self.assertEqual('cat@ap', repr(cat2.id_map.description))

        # Now create an ambiguous repr.
        tiger2 = subvols.apply_first_sendstream_item(si.subvol(
            path=b'tiger', uuid='eep', transid=3,
        ))
        self.assertEqual('tiger@ee-ERROR', repr(tiger.id_map.description))
        self.assertEqual('tiger@eep', repr(tiger2.id_map.description))

    def test_errors(self):
        si = SendStreamItems
        subvols = SubvolumeSet.new()

        with self.assertRaisesRegex(RuntimeError, 'must specify subvolume'):
            subvols.apply_first_sendstream_item(si.mkfile(path=b'foo'))

        with self.assertRaisesRegex(KeyError, 'lala-uuid-foo'):
            subvols.apply_first_sendstream_item(si.snapshot(
                path=b'x',
                uuid='y', transid=5,
                parent_uuid='lala-uuid-foo', parent_transid=3,
            ))

        def insert_cat(transid):
            subvols.apply_first_sendstream_item(si.subvol(
                path=b'cat', uuid='a', transid=transid,
            ))

        insert_cat(3)
        with self.assertRaisesRegex(RuntimeError, ' is already in use: '):
            insert_cat(555)


if __name__ == '__main__':
    unittest.main()
