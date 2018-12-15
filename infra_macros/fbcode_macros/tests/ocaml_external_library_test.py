# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class OcamlExternalLibraryTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_ocaml_external_library_parses(self, root):
        buckfile = "third-party-buck/default/build/supercaml/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:ocaml_external_library.bzl", "ocaml_external_library")
        ocaml_external_library(
            name = "re2",
            bytecode_libs = [
                "share/dotopam/default/lib/re2/re2.cma",
            ],
            c_libs = [
                "share/dotopam/default/lib/re2/libre2_stubs.a",
            ],
            include_dirs = [
                "share/dotopam/default/lib/re2",
            ],
            native_libs = [
                "share/dotopam/default/lib/re2/re2.cmxa",
            ],
            external_deps = [
                ("supercaml", None, "bin_prot"),
                ("re2", None, "re2"),
            ],
            native = False,
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                prebuilt_ocaml_library(
                  name = "re2",
                  bytecode_lib = "share/dotopam/default/lib/re2/re2.cma",
                  bytecode_only = True,
                  c_libs = [
                    "share/dotopam/default/lib/re2/libre2_stubs.a",
                  ],
                  include_dir = "share/dotopam/default/lib/re2",
                  lib_dir = "",
                  lib_name = "re2",
                  native_lib = "share/dotopam/default/lib/re2/re2.cmxa",
                  deps = [
                    "//third-party-buck/default/build/supercaml:bin_prot",
                    "//third-party-buck/default/build/re2:re2",
                    "//third-party-buck/default/build/supercaml:__project__",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
