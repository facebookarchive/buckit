# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CppLuaExtensionTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:cpp_lua_extension.bzl", "cpp_lua_extension")
    ]

    @tests.utils.with_project()
    def test_cpp_lua_extension_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:cpp_lua_extension.bzl", "cpp_lua_extension")

            cpp_lua_extension(
                name = "libspeech",
                srcs = [
                    "speech/init.c",
                ],
                headers = ["speech/init.h"],
                base_module = "",
                preprocessor_flags = [
                    "-DSPEECH",
                ],
                external_deps = [
                    ("fftw3", None),
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
