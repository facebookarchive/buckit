#!/usr/bin/env python3
import functools
import os
import sys
import tempfile
import unittest

from subvol_utils import Subvol

from .temp_subvolumes import TempSubvolumes


def with_temp_subvols(method):
    '''
    Any test that needs `self.temp_subvols` muse use this decorator.
    This is a cleaner alternative to doing this in setUp:

        self.temp_subvols.__enter__()
        self.addCleanup(self.temp_subvols.__exit__, None, None, None)

    The primary reason this is bad is explained in the TempSubvolumes
    docblock. It also fails to pass exception info to the __exit__.
    '''

    @functools.wraps(method)
    def decorated(self, *args, **kwargs):
        with TempSubvolumes(sys.argv[0]) as temp_subvols:
            return method(self, temp_subvols, *args, **kwargs)

    return decorated


class SubvolTestCase(unittest.TestCase):
    '''
    NB: The test here is partially redundant with demo_sendstreams, but
    coverage easier to manage when there's a clean, separate unit test.
    '''

    @with_temp_subvols
    def test_create_and_snapshot_and_already_exists(self, temp_subvols):
        p = temp_subvols.create('parent')
        p2 = Subvol(p.path(), already_exists=True)
        self.assertEqual(p.path(), p2.path())
        temp_subvols.snapshot(p2, 'child')

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

    @with_temp_subvols
    def test_run_as_root_input(self, temp_subvols):
        sv = temp_subvols.create('subvol')
        sv.run_as_root(['tee', sv.path('hello')], input=b'world')
        with open(sv.path('hello')) as infile:
            self.assertEqual('world', infile.read())

    @with_temp_subvols
    def test_mark_readonly_and_get_sendstream(self, temp_subvols):
        sv = temp_subvols.create('subvol')
        sv.run_as_root(['touch', sv.path('abracadabra')])
        sendstream = sv.mark_readonly_and_get_sendstream()
        self.assertIn(b'abracadabra', sendstream)
        with tempfile.TemporaryFile() as outfile:
            with sv.mark_readonly_and_write_sendstream_to_file(outfile):
                pass
            outfile.seek(0)
            self.assertEqual(sendstream, outfile.read())
