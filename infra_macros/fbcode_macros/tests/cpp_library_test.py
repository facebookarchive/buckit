# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CppLibraryTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")]

    @tests.utils.with_project()
    def test_cpp_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
            cpp_library(
                name = "util",
                srcs = [
                    "Utils.cpp",
                    "//foo:constants.cpp",
                ],
                headers = [
                    "Utils.h",
                ],
                deps = [
                    "//folly:json",
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
