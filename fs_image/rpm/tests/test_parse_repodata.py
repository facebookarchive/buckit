#!/usr/bin/env python3
import bz2
import gzip
import os
import unittest

from io import BytesIO
from typing import Iterator, Set, Tuple

from ..repo_objects import Repodata, RepoMetadata
from ..parse_repodata import get_rpm_parser, pick_primary_repodata
from ..tests.temp_repos import SAMPLE_STEPS, temp_repos_steps


def _listdir(path) -> Set[str]:
    return {os.path.join(path, p) for p in os.listdir(path)}


def find_test_repos(repos_root) -> Iterator[Tuple[str, RepoMetadata]]:
    for step_path in _listdir(repos_root):
        for p in _listdir(step_path):
            with open(os.path.join(p, 'repodata/repomd.xml'), 'rb') as f:
                yield p, RepoMetadata.new(xml=f.read())


def _rpm_set(infile: BytesIO, rd: Repodata):
    rpms = set()
    with get_rpm_parser(rd) as parser:
        while True:  # Exercise feed-in-chunks behavior
            chunk = infile.read(127)  # Our repodatas are tiny
            if not chunk:
                break
            rpms.update(parser.feed(chunk))
    assert len(rpms) > 0  # we have no empty test repos
    return rpms


class ParseRepodataTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Since we only read the repo, it is much faster to create
        # it once for all the tests (~2x speed-up as of writing).
        #
        # NB: This uses the fairly large "SAMPLE_STEPS" (instead of a more
        # minimal `repo_change_steps` used in most other tests) because it
        # **might** improve the tests' power.  This is NOT needed for code
        # coverage, so if you have a perf concern about this test, it is
        # fine to reduce the scope.
        cls.temp_repos_ctx = temp_repos_steps(repo_change_steps=SAMPLE_STEPS)
        cls.repos_root = cls.temp_repos_ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.temp_repos_ctx.__exit__(None, None, None)

    def _xml_and_sqlite_primaries(self, repomd: RepoMetadata) \
            -> Tuple[Repodata, Repodata]:
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
        unseen_steps = [{
            repo_name: True
                for repo_name, content in step.items()
                    if content is not None  # Means "delete repo"
        } for step in SAMPLE_STEPS]
        for repo_path, repomd in find_test_repos(self.repos_root):
            xml_rd, sql_rd = self._xml_and_sqlite_primaries(repomd)
            with open(os.path.join(repo_path, xml_rd.location), 'rb') as xf, \
                    open(os.path.join(repo_path, sql_rd.location), 'rb') as sf:
                sql_rpms = _rpm_set(sf, sql_rd)
                self.assertEqual(_rpm_set(xf, xml_rd), sql_rpms)

                # A joint test of repo parsing and `temp_repos`: check that
                # we had exactly the RPMs that were specified.
                step = int(os.path.basename(os.path.dirname(repo_path)))
                repo = os.path.basename(repo_path)  # `Repo` or `str` (name)
                # If it's an alias, search in `step`, not `last_step`, since
                # an alias refers to the step being queried, not the step
                # when it was established. NB: These semantics aren't in any
                # way "uniquely right", it is just what `temp_repos.py` does.
                while isinstance(repo, str):
                    repo_name = repo
                    # Find the most recent step that defined this repo name
                    last_step = step
                    while True:
                        repo = SAMPLE_STEPS[last_step].get(repo_name)
                        if repo is not None:
                            break
                        last_step -= 1
                        assert last_step >= 0
                self.assertEqual(
                    {
                        f'rpm-test-{r.name}-{r.version}-{r.release}.x86_64.rpm'
                            for r in repo.rpms
                    },
                    {os.path.basename(r.location) for r in sql_rpms},
                )
                unseen_steps[step].pop(os.path.basename(repo_path), None)
        self.assertEqual([], [s for s in unseen_steps if s])

    def test_pick_primary_and_errors(self):
        for _, repomd in find_test_repos(self.repos_root):
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
        for repo_path, repomd in find_test_repos(self.repos_root):
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
