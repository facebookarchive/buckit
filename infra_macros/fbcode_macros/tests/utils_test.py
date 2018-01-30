# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import re
import shutil
import subprocess
import textwrap

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

import tests.utils


class UtilsTest(tests.utils.TestCase):
    def test_run_unittests_runs_unittests(self):
        temp_dir = None
        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=True
        ) as project:
            temp_dir = project.project_path
            root_dir = os.path.join(temp_dir, "root")
            macros_dir = os.path.join(temp_dir, "fbcode_macros")
            buckd_dir = os.path.join(root_dir, ".buckd")

            root = project.root_cell
            self.assertTrue("fbcode_macros" in project.cells)
            root.add_directory("foo/bar/dir")
            root.add_file(
                "testing/file.bzl",
                textwrap.dedent(
                    """
                def identity(value):
                    return value
                def get_struct(**kwargs):
                    return struct(**kwargs)
                """
                ).strip()
            )
            root.add_resources_from("testdata/utils_test/sample.txt")
            root.update_buckconfig("foo", "bar", "baz")
            root.update_buckconfig("foo", "foobar", "baz")
            root.update_buckconfig_with_dict(
                {
                    "foo": {
                        "bar": "foobar1",
                        "baz": "foobar2"
                    },
                    "foo2": {
                        "bar2": ["baz2", "baz3"],
                    }
                }
            )
            ret = root.run_unittests(
                [("//testing:file.bzl", "identity", "get_struct")], [
                    "identity(1)", "identity(True)", 'get_struct(a="b")',
                    'identity(identity)', 'identity({"a": "b"})',
                    'identity([1,2,3])', 'identity(X)'
                ], 'X = "test_string"'
            )

            # Make sure our FS looks reasonable
            self.assertTrue(os.path.isdir(temp_dir))
            self.assertTrue(os.path.isdir(root_dir))

            file_bzl = os.path.join(root_dir, "testing", "file.bzl")
            self.assertTrue(os.path.isfile(file_bzl))
            with open(file_bzl, "r") as fin:
                self.assertEqual(
                    textwrap.dedent(
                        """
                def identity(value):
                    return value
                def get_struct(**kwargs):
                    return struct(**kwargs)
                """
                    ).strip(), fin.read()
                )

            sample_txt = os.path.join(
                root_dir, "testdata", "utils_test", "sample.txt"
            )
            self.assertTrue(os.path.isfile(sample_txt))
            with open(sample_txt, "r") as fin:
                self.assertEqual("This is a sample file", fin.read().strip())
            self.assertTrue(os.path.isdir(macros_dir))
            self.assertTrue(
                os.path.
                isfile(os.path.join(macros_dir, "build_defs", "config.bzl"))
            )
            self.assertEqual(
                os.path.join(project.project_path, "root"), root.full_path()
            )
            self.assertTrue(
                os.path.isdir(os.path.join(root_dir, "foo", "bar", "dir"))
            )

            # Double check buckconfig
            parser = configparser.ConfigParser()
            parser.read(os.path.join(root_dir, ".buckconfig"))

            self.assertEqual(
                "SKYLARK", parser.get("parser", "default_build_file_syntax")
            )
            self.assertEqual(
                "true", parser.get("parser", "polyglot_parsing_enabled")
            )
            self.assertEqual("foobar1", parser.get("foo", "bar"))
            self.assertEqual("foobar2", parser.get("foo", "baz"))
            self.assertEqual("baz", parser.get("foo", "foobar"))
            self.assertEqual("baz2,baz3", parser.get("foo2", "bar2"))

            # Check the output and parsing
            self.assertSuccess(ret)
            debug_pattern = r'^DEBUG:.* TEST_RESULT: "test_string"$'
            debug_pattern_found = next(
                (
                    line for line in ret.stderr.split("\n")
                    if re.match(debug_pattern, line)
                ), None
            ) is not None

            self.assertTrue(debug_pattern_found)
            self.assertEqual(7, len(ret.debug_lines))
            self.assertEqual(1, ret.debug_lines[0])
            self.assertIs(True, ret.debug_lines[1])
            self.assertEqual(self.struct(a="b"), ret.debug_lines[2])
            self.assertEqual("identity", ret.debug_lines[3].name)
            self.assertEqual({"a": "b"}, ret.debug_lines[4])
            self.assertEqual([1, 2, 3], ret.debug_lines[5])
            self.assertEqual("test_string", ret.debug_lines[6])

            self.assertFalse(os.path.exists(buckd_dir))

        # Make sure the FS goes away
        self.assertFalse(os.path.isdir(temp_dir))

    def test_runs_buckd_and_cleans_up(self):
        buckd_dir = None
        with tests.utils.Project(run_buckd=True) as project:
            buckd_dir = os.path.join(project.root_cell.full_path(), ".buckd")

            result = project.root_cell.run_unittests([], ["1"])
            self.assertSuccess(result)

            # Make sure that buck is running
            buckd_running = False
            for line in subprocess.check_output(["jps", "-v"]).split("\n"):
                if "-Dbuck.buckd_dir=" + buckd_dir in line:
                    buckd_running = True
            self.assertTrue(buckd_running)
            self.assertTrue(os.path.exists(buckd_dir))
        # Make sure that buck isn"t running
        for line in subprocess.check_output(["jps", "-v"]).split("\n"):
            self.assertNotIn("-Dbuck.buckd_dir=" + buckd_dir, line)
        self.assertFalse(os.path.exists(buckd_dir))

    def test_does_not_delete_if_not_requested(self):
        with tests.utils.Project(
            remove_files=False, add_fbcode_macros_cell=True
        ) as project:
            temp_dir = project.project_path
            project.root_cell.setup_all_filesystems()
            self.assertTrue(os.path.isdir(temp_dir))
        try:
            self.assertTrue(os.path.isdir(temp_dir))
        finally:
            shutil.rmtree(temp_dir)

    def test_does_not_add_macros_cell_if_not_requested(self):
        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=False
        ) as project:
            temp_dir = project.project_path
            project.root_cell.setup_all_filesystems()
            self.assertTrue(os.path.isdir(temp_dir))
            result = project.root_cell.run_unittests([], ["1"])
            self.assertSuccess(result)
            self.assertEqual(1, result.debug_lines[0])
            self.assertFalse(
                os.path.isfile(
                    os.path.
                    join(temp_dir, "fbcode_macros", "rule_defs", "config.bzl")
                )
            )
        self.assertFalse(os.path.isdir(temp_dir))
