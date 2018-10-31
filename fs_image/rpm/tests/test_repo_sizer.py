#!/usr/bin/env python3
import unittest

from ..common import Checksum
from ..repo_objects import Rpm
from ..repo_sizer import RepoSizer


class RepoSizerTestCase(unittest.TestCase):

    def test_sizer(self):
        sizer = RepoSizer()
        rpm1 = Rpm(
            size=1_000_000,
            checksum=Checksum('a1', 'a1v1'),
            canonical_checksum=None, location=None, build_timestamp=None,
        )
        sizer.visit_rpm(rpm1)

        # This changes best_checksum, so a synonym will be made.
        # Note that the size is initially incorrect.
        rpm2 = Rpm(
            size=1_000,
            checksum=Checksum('a1', 'a1v1'),
            canonical_checksum=Checksum('a2', 'a2v1'),
            location=None, build_timestamp=None,
        )
        self.assertNotEqual(rpm1.best_checksum(), rpm2.best_checksum())
        with self.assertRaisesRegex(AssertionError, ' other checksum '):
            sizer.visit_rpm(rpm2)
        sizer.visit_rpm(rpm2._replace(size=1_000_000))
        # These will also get mapped to the same synonym.
        sizer.visit_rpm(Rpm(
            size=1_000_000,
            checksum=Checksum('a1', 'a1v1'),
            canonical_checksum=None, location=None, build_timestamp=None,
        ))
        sizer.visit_rpm(Rpm(
            size=1_000_000,
            checksum=Checksum('a2', 'a2v1'),
            canonical_checksum=None, location=None, build_timestamp=None,
        ))
        self.assertEqual({'Rpm': 1_000_000}, sizer._get_classname_to_size())

        # Now we have two distinct checksum clusters.
        rpm3 = Rpm(
            size=1_000_000,
            canonical_checksum=Checksum('a4', 'a4v1'),
            checksum=Checksum('a3', 'a3v1'),
            location=None, build_timestamp=None,
        )
        sizer.visit_rpm(rpm3)
        with self.assertRaisesRegex(AssertionError, ' best checksum '):
            sizer.visit_rpm(rpm3._replace(size=123))
        self.assertEqual({'Rpm': 2_000_000}, sizer._get_classname_to_size())
        # Now, they got merged again
        sizer.visit_rpm(Rpm(
            size=1_000_000,
            canonical_checksum=Checksum('a1', 'a1v1'),
            checksum=Checksum('a4', 'a4v1'),
            location=None, build_timestamp=None,
        ))
        self.assertEqual({'Rpm': 1_000_000}, sizer._get_classname_to_size())

        # Add a couple of distinct RPMs
        sizer.visit_rpm(Rpm(
            size=234_000,
            checksum=Checksum('a1', 'a1v2'),
            canonical_checksum=None, location=None, build_timestamp=None,
        ))
        sizer.visit_rpm(Rpm(
            size=567,
            checksum=Checksum('a1', 'a1v3'),
            canonical_checksum=None, location=None, build_timestamp=None,
        ))
        self.assertEqual({'Rpm': 1_234_567}, sizer._get_classname_to_size())
        self.assertRegex(
            sizer.get_report('Msg'),
            '^Msg 1,234,567 bytes, by type: Rpm: 1,234,567$',
        )
