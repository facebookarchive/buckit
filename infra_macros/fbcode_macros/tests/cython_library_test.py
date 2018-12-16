# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CythonLibraryTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:cython_library.bzl", "cython_library")]

    @tests.utils.with_project()
    def test_cython_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:cython_library.bzl", "cython_library")
            cython_library(
                name = "foo",
                srcs = ["foo.pyx"],
                cpp_compiler_flags = ["-DFOO"],
                cpp_deps = [
                    "//:dep",
                ],
                cpp_external_deps = [
                    ("numpy", "any", "cpp"),
                    ("opencv3", None, "opencv_core"),
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
