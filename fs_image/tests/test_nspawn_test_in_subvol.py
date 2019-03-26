#!/usr/bin/env python3
import tempfile
import unittest

from nspawn_test_in_subvol import rewrite_test_cmd


class NspawnTestInSubvolTestCase(unittest.TestCase):

    def test_rewrite_cmd(self):
        bin = '/layer-test-binary'

        # Test no-op rewriting
        cmd = [bin, 'foo', '--bar', 'beep', '--baz', '-xack', '7', '9']
        with rewrite_test_cmd(cmd, next_fd=1337) as cmd_and_fd:
            self.assertEqual((cmd, None), cmd_and_fd)

        with tempfile.NamedTemporaryFile(suffix='.json') as t:
            prefix = ['--zap=3', '--ou', 'boo', '--ou=3']
            suffix = ['garr', '-abc', '-gh', '-d', '--e"f']
            with rewrite_test_cmd(
                [bin, *prefix, f'--output={t.name}', *suffix], next_fd=37,
            ) as (new_cmd, fd_to_forward):
                self.assertIsInstance(fd_to_forward, int)
                self.assertEqual([
                    '/bin/bash', '-c', ' '.join([
                        'exec',
                        bin, '--output', '>(cat >&37)', *prefix, *suffix[:-1],
                        # The last argument deliberately requires shell quoting.
                        """'--e"f'""",
                    ])
                ], new_cmd)
