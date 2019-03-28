#!/usr/bin/env python3
import unittest
import getpass

from coverage_test_helper import coverage_test_helper


class ImagePythonUnittestTest(unittest.TestCase):

    def test_container(self):
        # This should cause our 100% coverage assertion to pass.
        coverage_test_helper()
        self.assertEqual('nobody', getpass.getuser())
        # Container /logs should be writable
        with open('/logs/garfield', 'w') as catlog:
            catlog.write('Feed me.')
        # Future: add more assertions here as it becomes necessary what
        # aspects of test containers we actually care about.
