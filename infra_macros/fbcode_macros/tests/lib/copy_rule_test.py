# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CopyRuleTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:copy_rule.bzl", "copy_rule")]

    @tests.utils.with_project()
    def test_copy_rule_creates_genrules(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
        load("@fbcode_macros//build_defs/lib:copy_rule.bzl", "copy_rule")

        copy_rule(
            "$(location :foo)",
            "simple",
        )
        copy_rule(
            "$(location :foo)",
            "simple_with_out",
            out="some_out",
        )
        copy_rule(
            "$(location :foo)",
            "propagates_versions",
            propagate_versions=True,
        )
        """
            ),
        )

        expected = dedent(
            r"""
            cxx_genrule(
              name = "propagates_versions",
              cmd = "mkdir -p `dirname $OUT` && cp $(location :foo) $OUT",
              labels = [
                "is_fully_translated",
              ],
              out = "propagates_versions",
            )

            genrule(
              name = "simple",
              cmd = "mkdir -p `dirname $OUT` && cp $(location :foo) $OUT",
              labels = [
                "is_fully_translated",
              ],
              out = "simple",
            )

            genrule(
              name = "simple_with_out",
              cmd = "mkdir -p `dirname $OUT` && cp $(location :foo) $OUT",
              labels = [
                "is_fully_translated",
              ],
              out = "some_out",
            )
            """
        )

        result = root.runAudit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)
