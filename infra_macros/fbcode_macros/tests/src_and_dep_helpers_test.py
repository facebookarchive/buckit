# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class SrcAndDepHelpersTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
    ]

    @tests.utils.with_project()
    def test_extract_source_name_works(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    'src_and_dep_helpers.extract_source_name("//foo/bar:baz=path/to/baz1.cpp")',
                    'src_and_dep_helpers.extract_source_name(":baz=path/to/baz2.cpp")',
                    'src_and_dep_helpers.extract_source_name("path/to/baz3.cpp")',
                ],
            ),
            "path/to/baz1.cpp",
            "path/to/baz2.cpp",
            "path/to/baz3.cpp",
        )

    @tests.utils.with_project()
    def test_extract_source_name_fails_if_no_equals_sign(self, root):
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ['src_and_dep_helpers.extract_source_name("//foo:bar")']
            ),
            "generated source target //foo:bar is missing `=<name>` suffix",
        )

    @tests.utils.with_project()
    def test_convert_source_methods(self, root):
        commands = [
            'src_and_dep_helpers.convert_source("foo/bar", ":baz")',
            'src_and_dep_helpers.convert_source("foo/bar", "//other:baz")',
            'src_and_dep_helpers.convert_source("foo/bar", "foo/bar/baz.py")',
            'src_and_dep_helpers.convert_source("foo/bar", "foo.py")',
            'src_and_dep_helpers.convert_source_list("foo/bar", [":baz", "//other:baz", "foo/bar/baz.py", "foo.py"])',
            (
                'src_and_dep_helpers.convert_source_map("foo/bar", {'
                '":=bar/baz1.cpp": ":baz1.cpp",'
                '":=bar/baz2.cpp": "baz2.cpp",'
                '"bar/baz3.cpp": ":baz3.cpp",'
                '"bar/baz4.cpp": "baz4.cpp",'
                "})"
            ),
        ]

        expected = [
            "//foo/bar:baz",
            "//other:baz",
            "foo/bar/baz.py",
            "foo.py",
            ["//foo/bar:baz", "//other:baz", "foo/bar/baz.py", "foo.py"],
            {
                "bar/baz1.cpp": "//foo/bar:baz1.cpp",
                "bar/baz2.cpp": "baz2.cpp",
                "bar/baz3.cpp": "//foo/bar:baz3.cpp",
                "bar/baz4.cpp": "baz4.cpp",
            },
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_convert_source_map_handles_duplicate_keys(self, root):
        commands = [
            'src_and_dep_helpers.convert_source_map("foo/bar", {":=foo.cpp": "foo.cpp", "foo.cpp": "bar.cpp"})'
        ]
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands),
            'duplicate name "foo.cpp" for "bar.cpp" and "foo.cpp" in source map',
        )
