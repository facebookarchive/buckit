# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class SwigLibraryTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:swig_library.bzl", "swig_library")]

    @tests.utils.with_project()
    def test_swig_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:swig_library.bzl", "swig_library")
            swig_library(
                name = "foo_module",
                cpp_deps = [
                    ":some_cpp_dep",
                ],
                interface = "Foo.i",
                java_library_name = "FooLib",
                java_package = "org.example.foo",
                languages = [
                    "py",
                    "java",
                    "go",
                ],
                module = "Foo",
                py_base_module = "",
                go_package_name = "swig",
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
