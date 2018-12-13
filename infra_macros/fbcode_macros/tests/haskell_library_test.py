# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class HaskellLibraryTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:haskell_library.bzl", "haskell_library")]

    @tests.utils.with_project()
    def test_haskell_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:haskell_library.bzl", "haskell_library")
            # regular library
            haskell_library(
                name = "lib",
                srcs = [
                    "Lib.chs",
                ],
                packages = [],
                deps = [
                    ":lib_dep",
                ],
            )


            dll_config = {
                "traverse_fn": None,
                "type": "static",
            }

            # dll library
            haskell_library(
                name = "dll",
                srcs = ["Dll.hs"],
                dll = dll_config,
                packages = ["some_pkg"],
                deps = [":dll_dep"],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
