# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import platform

import tests.utils


class TargetUtilsTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:target_utils.bzl", "target_utils"),
        ("@fbcode_macros//build_defs:third_party.bzl", "third_party"),
    ]

    @tests.utils.with_project()
    def test_returns_proper_structs(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    'target_utils.RuleTarget("foo", "bar", "baz")',
                    'target_utils.RootRuleTarget("bar", "baz")',
                    'target_utils.ThirdPartyRuleTarget("bar", "baz")',
                    'target_utils.ThirdPartyToolRuleTarget("bar", "baz")',
                    'third_party.is_tp2_target(target_utils.RuleTarget("foo", "bar", "baz"))',
                    'third_party.is_tp2_target(target_utils.RootRuleTarget("bar", "baz"))',
                    'third_party.is_tp2_target(target_utils.ThirdPartyRuleTarget("bar", "baz"))',
                    'third_party.is_tp2_target(target_utils.ThirdPartyToolRuleTarget("bar", "baz"))',
                ],
            ),
            self.rule_target("foo", "bar", "baz"),
            self.rule_target(None, "bar", "baz"),
            self.rule_target("third-party", "bar", "baz"),
            self.rule_target("third-party-tools", "bar", "baz"),
            False,
            False,
            True,
            True,
        )

    @tests.utils.with_project()
    def test_is_rule_target(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    'target_utils.is_rule_target(target_utils.RuleTarget("foo", "bar", "baz"))',
                    'target_utils.is_rule_target(target_utils.RootRuleTarget("bar", "baz"))',
                    'target_utils.is_rule_target(target_utils.ThirdPartyRuleTarget("bar", "baz"))',
                    'target_utils.is_rule_target(target_utils.ThirdPartyToolRuleTarget("bar", "baz"))',
                    'target_utils.is_rule_target("1")',
                    "target_utils.is_rule_target(1)",
                    "target_utils.is_rule_target(True)",
                    "target_utils.is_rule_target(None)",
                ],
            ),
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            False,
        )

    @tests.utils.with_project()
    def test_parses_successfully(self, root):
        commands = [
            'target_utils.parse_target("@/third-party:llvm:bin/clang")',
            'target_utils.parse_target("@/third-party-tools:llvm:bin/clang")',
            'target_utils.parse_target(":foo-bar", default_base_path="parent/dir")',
            'target_utils.parse_target(":foo-bar-default", default_base_path="parent/dir", default_repo="default")',
            'target_utils.parse_target("some_cell//foo:bar")',
            'target_utils.parse_target("//foo:bar-default-none")',
            'target_utils.parse_target("//foo:bar-default", default_repo="default")',
        ]

        expected = [
            self.rule_target("third-party", "llvm", "bin/clang"),
            self.rule_target("third-party-tools", "llvm", "bin/clang"),
            self.rule_target(None, "parent/dir", "foo-bar"),
            self.rule_target("default", "parent/dir", "foo-bar-default"),
            self.rule_target("some_cell", "foo", "bar"),
            self.rule_target(None, "foo", "bar-default-none"),
            self.rule_target("default", "foo", "bar-default"),
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project(run_buckd=True)
    def test_parse_fails_when_given_bad_data(self, root):
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, ['target_utils.parse_target("invalid")']),
            'rule name must contain "//"',
        )
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ['target_utils.parse_target("@/third-party")']
            ),
            'rule name must contain at least one ":"',
        )
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, ['target_utils.parse_target(":foo::")']),
            'rule name has too many ":"',
        )

    @tests.utils.with_project()
    def test_external_dep_with_version(self, root):
        commands = [
            'target_utils.parse_external_dep("foo")',
            'target_utils.parse_external_dep("foo", "-py")',
            'target_utils.parse_external_dep(("foo",))',
            'target_utils.parse_external_dep(("foo",), "-py")',
            'target_utils.parse_external_dep(("foo", "1.0"))',
            'target_utils.parse_external_dep(("foo", "1.0"), "-py")',
            'target_utils.parse_external_dep(("foo", "1.0", "bar"))',
            'target_utils.parse_external_dep(("foo", None, "bar"))',
            'target_utils.parse_external_dep(("third-party-tools", "foo", "1.0", "bar"))',
            'target_utils.parse_external_dep(("third-party-tools", "foo", None, "bar"))',
        ]
        expected = [
            (self.rule_target("third-party", "foo", "foo"), None),
            (self.rule_target("third-party", "foo", "foo-py"), None),
            (self.rule_target("third-party", "foo", "foo"), None),
            (self.rule_target("third-party", "foo", "foo-py"), None),
            (self.rule_target("third-party", "foo", "foo"), "1.0"),
            (self.rule_target("third-party", "foo", "foo-py"), "1.0"),
            (self.rule_target("third-party", "foo", "bar"), "1.0"),
            (self.rule_target("third-party", "foo", "bar"), None),
            (self.rule_target("third-party-tools", "foo", "bar"), "1.0"),
            (self.rule_target("third-party-tools", "foo", "bar"), None),
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_parse_external_dep_fails_on_wrong_tuple_size(self, root):
        commands = [
            "target_utils.parse_external_dep("
            + '("foo", "bar", "baz", "other", "other foobar"))'
        ]
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands),
            "illegal external dependency ",
            "must have 1, 2, or 3 elements",
        )

    @tests.utils.with_project()
    def test_parse_external_dep_fails_on_bad_raw_target(self, root):
        commands = ['target_utils.parse_external_dep({"not_a_string": "or_tuple"})']
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands),
            "external dependency should be a tuple or string",
        )

    @tests.utils.with_project()
    def test_to_label_works(self, root):
        commands = [
            'target_utils.to_label("cell", "foo/bar", "baz")',
            'target_utils.to_label(None, "foo/bar", "baz")',
            'target_utils.to_label(None, "", "baz")',
        ]

        expected = ["cell//foo/bar:baz", "//foo/bar:baz", "//:baz"]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_target_to_label_works(self, root):
        commands = [
            'target_utils.target_to_label(target_utils.RootRuleTarget("foo", "bar"), platform="default")',
            'target_utils.target_to_label(target_utils.ThirdPartyRuleTarget("foo", "bar"), platform="default")',
            'target_utils.target_to_label(target_utils.parse_target("@/third-party:foo:bar"), platform="default")',
            'target_utils.target_to_label(target_utils.parse_target("@/third-party-tools:foo:bar"), platform="default")',
            'target_utils.target_to_label(target_utils.parse_target("cell//foo:bar"), platform="default")',
        ]

        expected = [
            "//foo:bar",
            "//third-party-buck/default/build/foo:bar",
            "//third-party-buck/default/build/foo:bar",
            "//third-party-buck/default/tools/foo:bar",
            "cell//foo:bar",
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
