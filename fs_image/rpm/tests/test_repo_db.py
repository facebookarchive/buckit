#!/usr/bin/env python3
import re
import unittest

from unittest import mock

from ..repo_db import RepoDBContext, SQLDialect
from ..repo_objects import RepoMetadata
from ..db_connection import DBConnectionContext


def _get_schema(conn):
    return conn.execute(
        'SELECT `name`, `sql` FROM `sqlite_master` where `type` = "table"'
    ).fetchall()


class RepoDBTestCase(unittest.TestCase):
    def setUp(self):
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

    def _check_schema(self, conn):
        for (a_name, a_sql), (e_name, e_sql) in zip(_get_schema(conn), [
            ('repo_metadata', (
                'CREATE TABLE `repo_metadata` ('
                ' `repo` BLOB NOT NULL,'
                ' `fetch_timestamp` INTEGER NOT NULL,'
                ' `build_timestamp` INTEGER NOT NULL,'
                ' `checksum` BLOB NOT NULL,'
                ' `xml` BLOB NOT NULL,'
                ' PRIMARY KEY (`repo`, `fetch_timestamp`),'
                ' UNIQUE (`repo`, `checksum`)'
                ' )'
            )),
        ]):
            self.assertEqual(e_name, a_name)
            self.assertEqual(e_sql, re.sub(r'\s+', ' ', a_sql))

    def _make_conn_ctx(self):
        return DBConnectionContext.make(kind='sqlite', db_path=':memory:')

    def test_create_tables(self):
        conn_ctx = self._make_conn_ctx()

        # At first, there are no tables.
        with conn_ctx as conn:
            self.assertEqual([], _get_schema(conn))

        # The two iterations test different scenarios:
        # 0: The tables already existed, creating the context again is a no-op.
        # 1: Creating the context will ensures that all tables exist.
        for _ in range(2):
            RepoDBContext(conn_ctx, SQLDialect.SQLITE3)
            with conn_ctx as conn:
                self._check_schema(conn)

    def _make_db_ctx(self, conn_ctx):
        return RepoDBContext(conn_ctx, SQLDialect.SQLITE3)

    def _fake_repomd(self, fetch_timestamp):
        repomd_xml = b'''
        <repomd>
          <data type="primary_db">
            <checksum type="fakealgo">fakesum</checksum>
            <location href="repodata/fakesum-primary.sqlite.bz2"/>
            <timestamp>12345</timestamp>
            <size>555555</size>
          </data>
        </repomd>
        '''
        with mock.patch('time.time') as mock_time:
            mock_time.return_value = fetch_timestamp
            repomd = RepoMetadata.new(xml=repomd_xml)
        return repomd

    def test_store_repomd_and_commit(self):
        repomd37 = self._fake_repomd(37)
        repomd73 = self._fake_repomd(73)
        self.assertGreater(repomd73.fetch_timestamp, repomd37.fetch_timestamp)

        conn_ctx = self._make_conn_ctx()
        # Exercise both the code path where our repomd to insert wins (gets
        # inserted), and the path where a racing writer had already inserted
        # the same repomd.
        for insert_repomd, db_repomd, do_commit in [
            (repomd37, repomd37, False),
            (repomd73, repomd73, False),
            (repomd37, repomd37, True),  # 37 is committed, won't be overwritten
            (repomd73, repomd37, False),
            (repomd73, repomd37, True),
            (repomd37, repomd37, True),
        ]:
            with self.subTest(
                insert_t=insert_repomd.fetch_timestamp,
                db_t=db_repomd.fetch_timestamp,
                do_commit=do_commit,
            ), self._make_db_ctx(conn_ctx) as db_ctx:
                self.assertEqual(
                    db_repomd.fetch_timestamp,
                    db_ctx.store_repomd('fake_repo', insert_repomd),
                )
                if do_commit:
                    db_ctx.commit()
