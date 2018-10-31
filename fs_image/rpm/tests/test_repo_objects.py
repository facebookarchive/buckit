#!/usr/bin/env python3
'There is not a whole lot to test, but this does get us basic coverage.'
import hashlib
import os
import unittest

from ..common import Checksum
from ..repo_objects import Rpm, RepoMetadata


class RepoObjectsTestCase(unittest.TestCase):

    def test_checksum(self):
        self.assertIs(
            type(hashlib.new('sha1')),
            type(Checksum(algorithm='sha', hexdigest=None).hasher()),
        )
        chk = Checksum(algorithm='sha256', hexdigest=None)
        h = chk.hasher()
        h.update(b'crouton')
        chk = chk._replace(hexdigest=h.hexdigest())
        self.assertEqual(chk, Checksum.from_string(str(chk)))

    def test_rpm(self):
        rpm = Rpm(
            location='a/b.rpm',
            checksum=Checksum.from_string('algo:fabcab'),
            canonical_checksum=None,
            size=14,
            build_timestamp=1337,
        )
        self.assertEqual(rpm.filename(), 'b.rpm')
        self.assertEqual('algo:fabcab', str(rpm.best_checksum()))
        self.assertEqual('zalgo:e1de41', str(rpm._replace(
            canonical_checksum=Checksum(algorithm='zalgo', hexdigest='e1de41'),
        ).best_checksum()))

    def test_repodata_and_metadata(self):
        with open(os.path.join(
            # This works in @mode/opt because test repos are baked into the PAR
            os.path.dirname(__file__),
            'repos/aarch64/0/dog/repodata/repomd.xml',
        ), 'rb') as infile:
            rmd = RepoMetadata.new(xml=infile.read())
            self.assertGreater(rmd.fetch_timestamp, rmd.build_timestamp)
            # If this assert fires, you are changing the canonical hash,
            # which is super-risky since it will break the existing DB.  So,
            # this test just exists to make sure you plan to migrate all the
            # canonical hashes in the database.
            self.assertEqual('sha384', rmd.checksum.algorithm)
            self.assertIs(rmd.checksum, rmd.best_checksum())
            self.assertEqual(1, sum(
                rd.is_primary_sqlite() for rd in rmd.repodatas
            ))
            self.assertEqual(1, sum(
                rd.is_primary_xml() for rd in rmd.repodatas
            ))
            for rd in rmd.repodatas:
                # The currently checked-in test repos all use sha256, which
                # seems to be the default for newer rpm tools.
                self.assertEqual('sha256', rd.checksum.algorithm)
                self.assertEqual(64, len(rd.checksum.hexdigest))
                self.assertLess(0, rd.size)
                self.assertLessEqual(rd.build_timestamp, rmd.build_timestamp)
                self.assertLess(0, rd.build_timestamp)
                self.assertIs(rd.checksum, rd.best_checksum())
