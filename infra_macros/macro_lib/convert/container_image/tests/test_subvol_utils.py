#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

from subvol_utils import Subvol

from .temp_subvolumes import TempSubvolumes


class SubvolTestCase(unittest.TestCase):
    '''
    NB: The test here is partially redundant with demo_sendstreams, but
    coverage easier to manage when there's a clean, separate unit test.
    '''

    def setUp(self):
        self.temp_subvols = TempSubvolumes(sys.argv[0])
        # This is not a great pattern because the temporary directory or
        # temporary subvolumes will not get exception information in
        # __exit__.  However, this avoids breaking the abstraction barriers
        # that e.g.  overloading `TestCase.run` would violate.
        self.temp_subvols.__enter__()
        self.addCleanup(self.temp_subvols.__exit__, None, None, None)

    def test_create_and_snapshot_and_already_exists(self):
        p = self.temp_subvols.create('parent')
        p2 = Subvol(p.path(), already_exists=True)
        self.assertEqual(p.path(), p.path())
        c = self.temp_subvols.snapshot(p2, 'child')

    def test_does_not_exist(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(AssertionError, 'No btrfs subvol'):
                Subvol(td, already_exists=True)

            sv = Subvol(td)
            with self.assertRaisesRegex(AssertionError, 'exists is False'):
                sv.run_as_root(['true'])

    def test_path(self):
        # We are only going to do path manipulations in this test.
        sv = Subvol('/subvol/need/not/exist')

        for bad_path in ['..', 'a/../../b/c/d', '../c/d/e']:
            with self.assertRaisesRegex(AssertionError, 'outside the subvol'):
                sv.path(bad_path)

        self.assertEqual(sv.path('a/b'), sv.path('/a/b/'))

        self.assertEqual(b'a/b', os.path.relpath(sv.path('a/b'), sv.path()))

        self.assertTrue(not sv.path('.').endswith(b'/.'))

    def test_mark_readonly_and_get_sendstream(self):
        sv = self.temp_subvols.create('subvol')
        sv.run_as_root(['touch', sv.path('abracadabra')])
        self.assertIn(b'abracadabra', sv.mark_readonly_and_get_sendstream())
