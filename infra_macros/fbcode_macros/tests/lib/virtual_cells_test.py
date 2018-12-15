# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import textwrap

import tests.utils


class PlatformTest(tests.utils.TestCase):

    includes = [
        ("@fbcode_macros//build_defs/lib:virtual_cells.bzl", "virtual_cells"),
        ("@fbcode_macros//build_defs/lib:rule_target_types.bzl", "rule_target_types"),
    ]

    @tests.utils.with_project()
    def test_translate_target(self, root):
        includes = self.includes + [(":defs.bzl", "VIRTUAL_CELLS")]
        root.addFile(
            "defs.bzl",
            textwrap.dedent(
                """
                load("@bazel_skylib//lib:partial.bzl", "partial")
                load("@fbcode_macros//build_defs/lib:rule_target_types.bzl", "rule_target_types")
                def _translate(base_path, name):
                    return rule_target_types.RuleTarget("xplat", "third-party/" + base_path, name)
                VIRTUAL_CELLS = {
                    "third-party": partial.make(_translate),
                }
                """
            ),
        )
        self.assertSuccess(
            root.runUnitTests(
                includes,
                [
                    textwrap.dedent(
                        """\
                        virtual_cells.translate_target(
                            VIRTUAL_CELLS,
                            rule_target_types.ThirdPartyRuleTarget("foo", "bar"),
                        )
                        """
                    )
                ],
            ),
            self.struct(base_path="third-party/foo", name="bar", repo="xplat"),
        )
