# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class GoUnittestTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_go_unittest_parses(self, root):
        buckfile = "testing/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:go_unittest.bzl", "go_unittest")
        go_unittest(
            name = "foo",
            srcs = ["test.go"],
            go_external_deps = ["golang.org/x/tools/go/vcs"],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                go_test(
                  name = "foo",
                  coverage_mode = "set",
                  platform = "default-gcc",
                  srcs = [
                    "test.go",
                  ],
                  deps = [
                    "//third-party-source/go/golang.org/x/tools/go/vcs:vcs",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )

                command_alias(
                  name = "foo-bench",
                  args = [
                    "-test.bench=.",
                    "-test.benchmem",
                  ],
                  exe = ":foo",
                  labels = [
                    "is_fully_translated",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
