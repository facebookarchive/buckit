# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class OcamlLibraryTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:ocaml_library.bzl", "ocaml_library")]

    @tests.utils.with_project()
    def test_ocaml_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:ocaml_library.bzl", "ocaml_library")
            ocaml_library(
                name = "foo",
                srcs = [
                    "foo.ml",
                    "thrift_IDL.ml",
                ],
                warnings_flags = "-27-42",
                deps = [
                    "//dep:hh_json",
                ],
                external_deps = [],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
