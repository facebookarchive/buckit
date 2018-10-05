#!/usr/bin/env python3
import bz2
import gzip
import os
import unittest

from io import BytesIO

from ..repo_objects import RepoMetadata
from ..parse_repodata import get_rpm_parser, pick_primary_repodata

# This works in @mode/opt because test repos are baked into the PAR
REPO_ROOT = os.path.join(os.path.dirname(__file__), 'repos/')


def _listdir(path) -> 'Set[str]':
    return {
        os.path.join(path, p)
            for p in os.listdir(path)
                # FB-internal Buck macros for Python create __init__.py
                # files inside the PAR-embedded repos :/
                if p != '__init__.py'
    }


def find_test_repos() -> 'Iterator[str, RepoMetadata]':
    for arch_path in _listdir(REPO_ROOT):
        for step_path in _listdir(arch_path):
            for p in _listdir(step_path):
                with open(os.path.join(p, 'repodata/repomd.xml'), 'rb') as f:
                    yield p, RepoMetadata.new(xml=f.read())


def _rpm_set(infile: 'BinaryIO', rd: 'Repodata'):
    rpms = set()
    with get_rpm_parser(rd) as parser:
        while True:  # Exercise feed-in-chunks behavior
            chunk = infile.read(127)  # Our repodatas are tiny
            if not chunk:
                break
            rpms.update(parser.feed(chunk))
    assert len(rpms) > 0  # we have no empty test repos
    # Future: consider asserting that we actually had the right RPMs?
    return rpms


class ParseRepodataTestCase(unittest.TestCase):

    def _xml_and_sqlite_primaries(self, repomd: RepoMetadata) \
            -> 'Tuple[Repodata, Repodata]':
        primaries = [
            (rd.is_primary_sqlite(), rd.is_primary_xml(), rd)
                for rd in repomd.repodatas
                    if rd.is_primary_sqlite() or rd.is_primary_xml()
        ]
        primaries.sort()
        # All our test repos have both SQLite and XML generated.
        self.assertEqual(
            [(False, True), (True, False)],
            [(sql, xml) for sql, xml, _ in primaries],
        )
        return (rd for _, _, rd in primaries)

    def test_parsers_have_same_output(self):
        for repo_path, repomd in find_test_repos():
            xml_rd, sql_rd = self._xml_and_sqlite_primaries(repomd)
            with open(os.path.join(repo_path, xml_rd.location), 'rb') as xf, \
                    open(os.path.join(repo_path, sql_rd.location), 'rb') as sf:
                self.assertEqual(_rpm_set(xf, xml_rd), _rpm_set(sf, sql_rd))

    def test_pick_primary_and_errors(self):
        for _, repomd in find_test_repos():
            xml_rd, sql_rd = self._xml_and_sqlite_primaries(repomd)
            self.assertIs(sql_rd, pick_primary_repodata(repomd.repodatas))
            self.assertIs(xml_rd, pick_primary_repodata(
                [rd for rd in repomd.repodatas if rd is not sql_rd]
            ))
            with self.assertRaisesRegex(RuntimeError, '^More than one primar'):
                self.assertIs(xml_rd, pick_primary_repodata(
                    [sql_rd, *repomd.repodatas]
                ))
            non_primary_rds = [
                rd for rd in repomd.repodatas if rd not in [sql_rd, xml_rd]
            ]
            with self.assertRaisesRegex(RuntimeError, ' no known primary '):
                self.assertIs(xml_rd, pick_primary_repodata(non_primary_rds))
            with self.assertRaisesRegex(AssertionError, 'Not reached'):
                get_rpm_parser(non_primary_rds[0])

    def test_sqlite_edge_cases(self):
        for repo_path, repomd in find_test_repos():
            _, sql_rd = self._xml_and_sqlite_primaries(repomd)
            with open(os.path.join(repo_path, sql_rd.location), 'rb') as sf:
                bz_data = sf.read()
            # Some in-the-wild primary SQLite dbs are .gz, while all of ours
            # are .bz2, so let's recompress.
            gzf = BytesIO()
            with gzip.GzipFile(fileobj=gzf, mode='wb') as gz_out:
                gz_out.write(bz2.decompress(bz_data))
            gzf.seek(0)
            self.assertEqual(
                _rpm_set(gzf, sql_rd._replace(location='X-primary.sqlite.gz')),
                _rpm_set(BytesIO(bz_data), sql_rd),
            )
            with self.assertRaisesRegex(RuntimeError, '^Unused data after '):
                _rpm_set(BytesIO(bz_data + b'oops'), sql_rd)
            with self.assertRaisesRegex(RuntimeError, 'archive is incomplete'):
                _rpm_set(BytesIO(bz_data[:-5]), sql_rd)
