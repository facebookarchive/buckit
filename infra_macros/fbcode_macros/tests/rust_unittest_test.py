# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class RustUnittestTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:rust_unittest.bzl", "rust_unittest")]

    @tests.utils.with_project()
    def test_rust_unittest_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:rust_unittest.bzl", "rust_unittest")
            rust_unittest(
                name = "util",
                srcs = ["test.rs"],
                deps = ["//rust:json"],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
