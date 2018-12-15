# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class PythonUnittestTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")]

    @tests.utils.with_project()
    def test_python_unittest_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")
            python_unittest(
                name = "my_python_test",
                base_module = "terrible.feature",
                cpp_deps = ["//:cpp_lib"],
                deps = ["//:python_lib"],
                external_deps = [
                    "pyyaml",
                    ("six", None, "six"),
                ],
                gen_srcs = ["//:deprecated=feature.py"],
                py_flavor = "",
                resources = {"src.py": "dest.py"},
                srcs = [
                    "not_a_python_source",
                    "src.py",
                ],
                tags = ["foo"],
                tests = ["//:python_lib_test"],
                typing = True,
                typing_options = "pyre",
                versioned_srcs = [(">2", ["new.py"])],

                needed_coverage = [(50, "//foo:bar_lib")],
                emails = ["dev@example.com"],
                additional_coverage_targets = [],
                allocator = "jemalloc",
                analyze_imports = True,
                argcomplete = True,
                check_types = True,
                check_types_options = "",
                compile = True,
                helper_deps = True,
                jemalloc_conf = None,
                main_module = "foo.bar.module",
                par_style = "xar",
                preload_deps = [],
                py_version = ">3",
                strict_tabs = True,
                strip_libpar = True,

            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
