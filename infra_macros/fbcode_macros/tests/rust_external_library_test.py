# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class RustExternalLibraryTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_rust_external_library_parses(self, root):
        buckfile = "third-party-buck/default/build/foo/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:rust_external_library.bzl", "rust_external_library")
        rust_external_library(
            name = "libsqlite3-sys-0.9.3",
            crate = "libsqlite3_sys",
            # MIT
            licenses = ["licenses/MIT/MIT.txt"],
            rlib = "rlib/liblibsqlite3_sys-104f194a162d4a87.rlib",
            visibility = None,
            deps = [
                ":pkg-config-0.3.14",
            ],
            external_deps = [
                ("sqlite", None, "sqlite"),
            ],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                prebuilt_rust_library(
                  name = "libsqlite3-sys-0.9.3",
                  crate = "libsqlite3_sys",
                  licenses = [
                    "licenses/MIT/MIT.txt",
                  ],
                  rlib = "rlib/liblibsqlite3_sys-104f194a162d4a87.rlib",
                  deps = [
                    "//third-party-buck/default/build/foo:pkg-config-0.3.14",
                    "//third-party-buck/default/build/sqlite:sqlite",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
