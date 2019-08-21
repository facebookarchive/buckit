#!/usr/bin/env python3
import time
import unittest

from ..common import Checksum, log as common_log, retry_fn, RpmShard


class TestCommon(unittest.TestCase):


    def test_rpm_shard(self):
        self.assertEqual(
            RpmShard(shard=3, modulo=7), RpmShard.from_string('3:7'),
        )

        class FakeRpm:
            def __init__(self, filename):
                self._filename = filename

            def filename(self):
                return self._filename

        self.assertEqual(
            [('foo', True), ('bar', False), ('foo', False), ('bar', True)],
            [
                (rpm, shard.in_shard(FakeRpm(rpm)))
                    for shard in [RpmShard(1, 7), RpmShard(2, 7)]
                        for rpm in ['foo', 'bar']
            ],
        )

    def test_checksum(self):
        cs = Checksum(algorithm='oops', hexdigest='dada')
        self.assertEqual('oops:dada', str(cs))
        self.assertEqual(cs, Checksum.from_string(str(cs)))
        for algo in ['sha1', 'sha']:
            h = Checksum(algo, 'ignored').hasher()
            h.update(b'banana')
            self.assertEqual(
                '250e77f12a5ab6972a0895d290c4792f0a326ea8', h.hexdigest(),
            )

    def test_retry_fn(self):

        class Retriable:
            def __init__(self, attempts_to_fail=0):
                self.attempts = 0
                self.first_success_attempt = attempts_to_fail + 1

            def run(self):
                self.attempts += 1
                if self.attempts >= self.first_success_attempt:
                    return self.attempts
                raise RuntimeError(self.attempts)

        self.assertEqual(1, retry_fn(
            Retriable().run, delays=[], what='succeeds immediately'
        ))

        # Check log messages, and ensure that delays add up as expected
        start_time = time.time()
        with self.assertLogs(common_log) as log_ctx:
            self.assertEqual(4, retry_fn(
                Retriable(3).run, delays=[0, 0.1, 0.2], what='succeeds on try 4'
            ))
        self.assertTrue(any(
            '\n[Retry 3 of 3] succeeds on try 4 -- waiting 0.2 seconds.\n' in o
                for o in log_ctx.output
        ))
        self.assertGreater(time.time() - start_time, 0.3)

        # Check running out of retries
        with self.assertLogs(common_log) as log_ctx, \
                self.assertRaises(RuntimeError) as ex_ctx:
            retry_fn(Retriable(100).run, delays=[0] * 7, what='never succeeds')
        self.assertTrue(any(
            '\n[Retry 7 of 7] never succeeds -- waiting 0 seconds.\n' in o
                for o in log_ctx.output
        ))
        self.assertEqual((8,), ex_ctx.exception.args)
