# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CppLibraryExternalCustomTest(tests.utils.TestCase):
    includes = [
        (
            "@fbcode_macros//build_defs:cpp_library_external_custom.bzl",
            "cpp_library_external_custom",
        )
    ]

    @tests.utils.with_project()
    def test_cpp_library_external_custom_parses(self, root):
        root.addFile(
            "third-party-buck/bar/baz/BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:cpp_library_external_custom.bzl", "cpp_library_external_custom")
            cpp_library_external_custom(
                name = "mkl_lp64_iomp",
                include_dir = "mkl/include",
                lib_dir = "mkl/lib/intel64",
                propagated_pp_flags = [],
                shared_libs = [
                    "mkl_intel_lp64",
                    "mkl_intel_thread",
                    "mkl_core",
                    "mkl_def",
                ],
                shared_link = [
                    "-L{dir}",
                    "-l{lib_mkl_core}",
                    "-L{dir}",
                    "-l{lib_mkl_intel_lp64}",
                    "-L{dir}",
                    "-l{lib_mkl_intel_thread}",
                ],
                static_pic_libs = [
                    "mkl_intel_lp64",
                    "mkl_core",
                    "mkl_intel_thread",
                ],
                static_pic_link = [
                    "--start-group",
                    "{LIB_mkl_intel_lp64}",
                    "{LIB_mkl_core}",
                    "{LIB_mkl_intel_thread}",
                    "--end-group",
                ],
                external_deps = [
                    ("glibc", None, "pthread"),
                    ("glibc", None, "dl"),
                    ("glibc", None, "m"),
                    ("IntelComposerXE", None, "iomp5"),
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["third-party-buck/bar/baz/BUCK"]))
