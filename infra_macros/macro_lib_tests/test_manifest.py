#!/usr/bin/env python3
from pathlib import Path
import unittest


class ManifestTestCase(unittest.TestCase):

    def test_manifest(self):
        import __manifest__

        self.assertEqual(__manifest__.__name__, "__manifest__")

        path = Path(__manifest__.__file__)
        self.assertTrue(path.is_file(), f"{path} is not a file")
        while path.suffixes:
            path = path.with_suffix("")
        self.assertTrue(path.name == "__manifest__")

        self.assertEqual(__manifest__.fbmake["build_tool"], "buck")
        self.assertIn(
            __manifest__.fbmake["main_module"],
            {"__test_main__", "__fb_test_main__"},
        )
        for module in __manifest__.modules:
            if module.endswith("macro_lib_tests.test_manifest"):
                break
        else:
            self.fail("test_manifest not found in __manifest__.modules")
