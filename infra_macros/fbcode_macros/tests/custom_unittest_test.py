# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CustomUnittestTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:custom_unittest.bzl", "custom_unittest")]

    @tests.utils.with_project()
    def test_rust_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:custom_unittest.bzl", "custom_unittest")
            custom_unittest(
                name = "foo",
                command = [
                    "$(location :some_test)",
                    "$(location :some_target)",
                ],
                type = "simple",
                deps = [
                    ":some_test",
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
