# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class SrcAndDepHelpersTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers"),
        ("@fbcode_macros//build_defs:target_utils.bzl", "target_utils"),
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

    @tests.utils.with_project()
    def test_parse_source_methods(self, root):
        commands = [
            'src_and_dep_helpers.parse_source("foo/bar", "@/third-party:foo:baz")',
            'src_and_dep_helpers.parse_source("foo/bar", ":baz")',
            'src_and_dep_helpers.parse_source("foo/bar", "//other:baz")',
            'src_and_dep_helpers.parse_source("foo/bar", "src.cpp")',
            'src_and_dep_helpers.parse_source_list("foo/bar", [":baz", "//other:baz", "src.cpp"])',
            (
                'src_and_dep_helpers.parse_source_map("foo/bar", {'
                '"baz1.cpp": ":baz1.cpp",'
                '"baz2.cpp": "//other:baz2.cpp",'
                '"baz3.cpp": "baz3.cpp",'
                "})"
            ),
        ]

        expected = [
            self.rule_target("third-party", "foo", "baz"),
            self.rule_target(None, "foo/bar", "baz"),
            self.rule_target(None, "other", "baz"),
            "src.cpp",
            [
                self.rule_target(None, "foo/bar", "baz"),
                self.rule_target(None, "other", "baz"),
                "src.cpp",
            ],
            {
                "baz1.cpp": self.rule_target(None, "foo/bar", "baz1.cpp"),
                "baz2.cpp": self.rule_target(None, "other", "baz2.cpp"),
                "baz3.cpp": "baz3.cpp",
            },
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_format_platform_param_works(self, root):
        includes = self.includes + [
            (":defs.bzl", "a_func"),
            ("@bazel_skylib//lib:partial.bzl", "partial"),
        ]
        root.addFile(
            "defs.bzl",
            dedent(
                """
        def a_func(prepend, platform, compiler):
            return "{}-{}-{}".format(prepend, platform, compiler)
        """
            ),
        )
        commands = [
            'src_and_dep_helpers.format_platform_param(partial.make(a_func, "foo"))',
            'src_and_dep_helpers.format_platform_param("some_stuff")',
        ]
        expected = [
            [
                ("^default-clang$", "foo-default-clang"),
                ("^default-gcc$", "foo-default-gcc"),
                ("^gcc5-clang$", "foo-gcc5-clang"),
                ("^gcc5-gcc$", "foo-gcc5-gcc"),
                ("^gcc6-clang$", "foo-gcc6-clang"),
                ("^gcc6-gcc$", "foo-gcc6-gcc"),
                ("^gcc7-clang$", "foo-gcc7-clang"),
                ("^gcc7-gcc$", "foo-gcc7-gcc"),
            ],
            [
                ("^default-clang$", "some_stuff"),
                ("^default-gcc$", "some_stuff"),
                ("^gcc5-clang$", "some_stuff"),
                ("^gcc5-gcc$", "some_stuff"),
                ("^gcc6-clang$", "some_stuff"),
                ("^gcc6-gcc$", "some_stuff"),
                ("^gcc7-clang$", "some_stuff"),
                ("^gcc7-gcc$", "some_stuff"),
            ],
        ]

        result = root.runUnitTests(includes, commands)
        self.assertSuccess(result)
        sorted_result = [sorted(lines) for lines in result.debug_lines]
        self.assertEqual(expected, sorted_result)

    @tests.utils.with_project()
    def test_format_deps_works(self, root):
        commands = [
            'src_and_dep_helpers.format_deps([target_utils.RootRuleTarget("foo/bar", "baz")])',
            'src_and_dep_helpers.format_deps([target_utils.RuleTarget("xplat", "foo/bar", "baz")])',
            'src_and_dep_helpers.format_deps([target_utils.ThirdPartyRuleTarget("foo", "baz")], "default")',
        ]
        expected = [
            ["//foo/bar:baz"],
            ["xplat//foo/bar:baz"],
            ["//third-party-buck/default/build/foo:baz"],
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_format_platform_deps_works(self, root):
        commands = [
            (
                "src_and_dep_helpers.format_platform_deps(["
                'target_utils.RootRuleTarget("foo/bar", "baz"),'
                'target_utils.RuleTarget("xplat", "foo/bar", "baz"),'
                'target_utils.ThirdPartyRuleTarget("foo", "baz"),'
                "])"
            )
        ]
        expected = [
            [
                (
                    "^default-clang$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/default/build/foo:baz",
                    ],
                ),
                (
                    "^default-gcc$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/default/build/foo:baz",
                    ],
                ),
                (
                    "^gcc5-clang$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/gcc5/build/foo:baz",
                    ],
                ),
                (
                    "^gcc5-gcc$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/gcc5/build/foo:baz",
                    ],
                ),
                (
                    "^gcc6-clang$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/gcc6/build/foo:baz",
                    ],
                ),
                (
                    "^gcc6-gcc$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/gcc6/build/foo:baz",
                    ],
                ),
                (
                    "^gcc7-clang$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/gcc7/build/foo:baz",
                    ],
                ),
                (
                    "^gcc7-gcc$",
                    [
                        "//foo/bar:baz",
                        "xplat//foo/bar:baz",
                        "//third-party-buck/gcc7/build/foo:baz",
                    ],
                ),
            ]
        ]

        result = root.runUnitTests(self.includes, commands)
        self.assertSuccess(result)
        sorted_result = [sorted(lines) for lines in result.debug_lines]
        self.assertEqual(expected, sorted_result)

    @tests.utils.with_project()
    def test_format_all_deps_works(self, root):
        commands = [
            (
                "src_and_dep_helpers.format_all_deps(["
                'target_utils.RootRuleTarget("foo/bar", "baz"),'
                'target_utils.RuleTarget("xplat", "foo/bar", "baz"),'
                'target_utils.ThirdPartyRuleTarget("foo", "baz"),'
                "])"
            ),
            (
                "src_and_dep_helpers.format_all_deps(["
                'target_utils.RootRuleTarget("foo/bar", "baz"),'
                'target_utils.RuleTarget("xplat", "foo/bar", "baz"),'
                'target_utils.ThirdPartyRuleTarget("foo", "baz"),'
                '], platform="gcc5")'
            ),
        ]
        expected = [
            (
                ["//foo/bar:baz", "xplat//foo/bar:baz"],
                [
                    ("^default-clang$", ["//third-party-buck/default/build/foo:baz"]),
                    ("^default-gcc$", ["//third-party-buck/default/build/foo:baz"]),
                    ("^gcc5-clang$", ["//third-party-buck/gcc5/build/foo:baz"]),
                    ("^gcc5-gcc$", ["//third-party-buck/gcc5/build/foo:baz"]),
                    ("^gcc6-clang$", ["//third-party-buck/gcc6/build/foo:baz"]),
                    ("^gcc6-gcc$", ["//third-party-buck/gcc6/build/foo:baz"]),
                    ("^gcc7-clang$", ["//third-party-buck/gcc7/build/foo:baz"]),
                    ("^gcc7-gcc$", ["//third-party-buck/gcc7/build/foo:baz"]),
                ],
            ),
            (
                [
                    "//foo/bar:baz",
                    "xplat//foo/bar:baz",
                    "//third-party-buck/gcc5/build/foo:baz",
                ],
                [],
            ),
        ]

        result = root.runUnitTests(self.includes, commands)
        self.assertSuccess(result)
        sorted_result = [(lines[0], sorted(lines[1])) for lines in result.debug_lines]
        self.assertEqual(expected, sorted_result)

    @tests.utils.with_project()
    def test_normalize_external_dep(self, root):
        commands = [
            'src_and_dep_helpers.normalize_external_dep(("foo", None, "bar"))',
            'src_and_dep_helpers.normalize_external_dep(("foo", "1.0", "bar"), parse_version=True)',
        ]
        expected = [
            self.rule_target("third-party", "foo", "bar"),
            (self.rule_target("third-party", "foo", "bar"), "1.0"),
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
