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
import stat
import subprocess

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

import tests.utils
from tests.utils import dedent


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
            self.assertIn("fbcode_macros", project.cells)
            root.addDirectory("foo/bar/dir")
            root.addFile(
                "testing/file.bzl",
                dedent(
                    """
                def identity(value):
                    return value
                def get_struct(**kwargs):
                    return struct(**kwargs)
                """
                )
            )
            root.addResourcesFrom("testdata/utils_test/sample.txt")
            root.updateBuckconfig("foo", "bar", "baz")
            root.updateBuckconfig("foo", "foobar", "baz")
            root.updateBuckconfigWithDict(
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
            ret = root.runUnitTests(
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
                    dedent(
                        """
                def identity(value):
                    return value
                def get_struct(**kwargs):
                    return struct(**kwargs)
                """
                    ), fin.read()
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
                os.path.join(project.project_path, "root"), root.fullPath()
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
        for dir in os.environ["PATH"].split(os.pathsep):
            if os.path.exists(os.path.join(dir, "jps")):
                break
        else:
            self.skipTest("Could not find jps")

        buckd_dir = None
        with tests.utils.Project(run_buckd=True) as project:
            buckd_dir = os.path.join(project.root_cell.fullPath(), ".buckd")

            result = project.root_cell.runUnitTests([], ["1"])
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
            project.root_cell.setupAllFilesystems()
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
            project.root_cell.setupAllFilesystems()
            self.assertTrue(os.path.isdir(temp_dir))
            result = project.root_cell.runUnitTests([], ["1"])
            self.assertSuccess(result)
            self.assertEqual(1, result.debug_lines[0])
            self.assertFalse(
                os.path.isfile(
                    os.path.
                    join(temp_dir, "fbcode_macros", "rule_defs", "config.bzl")
                )
            )
        self.assertFalse(os.path.isdir(temp_dir))

    def test_validating_audit_works(self):
        with self.assertRaises(AssertionError) as e:
            result = tests.utils.AuditTestResult(1, "", "", {})
            expected = {}
            self.validateAudit(expected, result)
        self.assertIn("Expected zero return code", str(e.exception))

        with self.assertRaises(AssertionError) as e:
            result = tests.utils.AuditTestResult(
                0, "", "", {"foo/BUCK": None,
                            "bar/BUCK": ""}
            )
            expected = {"foo/BUCK": "", "bar/BUCK": ""}
            self.validateAudit(expected, result)
        self.assertIn(
            "Got a list of files that had empty contents: ", str(e.exception)
        )
        self.assertIn("foo/BUCK", str(e.exception))

        with self.assertRaises(AssertionError) as e:
            result = tests.utils.AuditTestResult(
                0, "", "", {"foo/BUCK": "",
                            "bar/BUCK": ""}
            )
            expected = {"foo/BUCK": "", "baz/BUCK": ""}
            self.validateAudit(expected, result)
        self.assertTrue(
            "Parsed list of files != expected list of files" in
            str(e.exception)
        )
        self.assertIn("bar/BUCK", str(e.exception))
        self.assertIn("baz/BUCK", str(e.exception))

        with self.assertRaises(AssertionError) as e:
            result = tests.utils.AuditTestResult(
                0, "", "",
                {"foo/BUCK": "foo\nbar\nbaz\n",
                 "bar/BUCK": "baz\nfoo\nbar\n"}
            )
            expected = {
                "foo/BUCK": "foo\nbar\nbaz\n",
                "bar/BUCK": "foo\nbar\nbaz\n"
            }
            self.validateAudit(expected, result)
        self.assertIn("Content of bar/BUCK differs:", str(e.exception))
        self.assertIn("bar/BUCK", str(e.exception))

    def test_parses_audit_results_properly(self):
        with tests.utils.Project(remove_files=False) as project:
            root = project.root_cell
            root.addFile(
                "foo/main.cpp",
                dedent(
                    """\
            #include "bar/lib.h"
            int main() { bar::f(); return 0; } }
            """
                )
            )
            root.addFile(
                "bar/lib.h",
                dedent(
                    """\
            #pragma once
            namespace bar { void f(); }
            """
                )
            )
            root.addFile(
                "bar/lib.cpp",
                dedent(
                    """\
            #include "bar/lib.h"
            namespace bar { void f() { return; } }
            """
                )
            )
            root.addFile(
                "bar/BUCK",
                dedent(
                    """\
            cxx_library(
                name="lib",
                exported_headers=["lib.h"],
                srcs=["lib.cpp"],
                visibility=["PUBLIC"],
            )
            """
                )
            )
            root.addFile(
                "foo/BUCK",
                dedent(
                    """\
            cxx_binary(
                name="main",
                srcs=["main.cpp"],
                deps=["//bar:lib"],
            )
            """
                )
            )

            expected = {
                "foo/BUCK":
                dedent(
                    """\
                    cxx_binary(
                      name = "main",
                      srcs = [
                        "main.cpp",
                      ],
                      deps = [
                        "//bar:lib",
                      ],
                    )
                    """
                ),
                "bar/BUCK":
                dedent(
                    """\
                    cxx_library(
                      name = "lib",
                      exportedHeaders = [
                        "lib.h",
                      ],
                      srcs = [
                        "lib.cpp",
                      ],
                      visibility = [
                        "PUBLIC",
                      ],
                    )
                    """
                )
            }

            ret = root.runAudit(["foo/BUCK", "bar/BUCK"])

            self.validateAudit(expected, ret)

    def test_assert_success_fails_on_invalid_return(self):
        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=True
        ) as project:
            root = project.root_cell
            ret = root.runUnitTests([], ['"string1"', '"string3"'])
            with self.assertRaises(AssertionError):
                self.assertSuccess(ret, "string1", "string2")

    def test_assert_failure_fails_with_success(self):
        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=True
        ) as project:
            root = project.root_cell
            ret = root.runUnitTests([], ['"string1"', '"string3"'])
            with self.assertRaises(AssertionError):
                self.assertFailureWithMessage(ret, "string1")

    def test_assert_failure_fails_with_bad_message(self):
        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=True
        ) as project:
            root = project.root_cell
            ret = root.runUnitTests([], ['"string1"', '"string3" +'])
            with self.assertRaises(AssertionError):
                self.assertFailureWithMessage(ret, "WTF")

    def test_assert_failure_passes_with_right_message(self):
        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=True
        ) as project:
            root = project.root_cell
            ret = root.runUnitTests(
                [], ['"string1"', '"string3"'], 'fail("WTF")'
            )
            self.assertFailureWithMessage(ret, "WTF")

    def test_adding_executable_file_makes_it_executable(self):
        def is_executable(path):
            return (os.stat(path).st_mode & stat.S_IXUSR) != 0

        with tests.utils.Project(
            remove_files=True, add_fbcode_macros_cell=True
        ) as project:
            root = project.root_cell
            root.addFile('foo.sh', 'echo "foo"', executable=True)
            root.addFile('bar.sh', 'echo "bar"', executable=False)
            root.addFile('baz.sh', 'echo "baz"', executable=False)
            root.setupAllFilesystems()
            self.assertTrue(
                is_executable(os.path.join(root.fullPath(), 'foo.sh')))
            self.assertFalse(
                is_executable(os.path.join(root.fullPath(), 'bar.sh')))
            self.assertFalse(
                is_executable(os.path.join(root.fullPath(), 'baz.sh')))
