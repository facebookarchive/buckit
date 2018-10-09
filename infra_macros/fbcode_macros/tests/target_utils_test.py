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
