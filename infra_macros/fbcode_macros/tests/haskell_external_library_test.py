# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import os

import tests.utils
from tests.utils import dedent


class HaskellExternalLibraryTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_haskell_external_library_parses(self, root):
        buckfile = "third-party-buck/gcc5/build/ghc/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
        haskell_external_library(
            name = "process",
            db = "lib/package.conf.d",
            id = "process-1.4.3.0",
            include_dirs = [
                "lib/process-1.4.3.0/include",
            ],
            lib_dir = "lib/process-1.4.3.0",
            libs = ["HSprocess-1.4.3.0"],
            version = "1.4.3.0",
            external_deps = [
                ("ghc", None, "base"),
            ],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                haskell_prebuilt_library(
                  name = "process",
                  cxx_header_dirs = [
                    "lib/process-1.4.3.0/include",
                  ],
                  db = "lib/package.conf.d",
                  exported_compiler_flags = [
                    "-expose-package",
                    "process-1.4.3.0",
                  ],
                  exported_linker_flags = [
                    "-Wl,--no-as-needed",
                  ],
                  id = "process-1.4.3.0",
                  profiled_static_libs = [
                    "lib/process-1.4.3.0/libHSprocess-1.4.3.0_p.a",
                  ],
                  shared_libs = {
                    "libHSprocess-1.4.3.0-ghc8.0.2.so": "lib/process-1.4.3.0/libHSprocess-1.4.3.0-ghc8.0.2.so",
                  },
                  static_libs = [
                    "lib/process-1.4.3.0/libHSprocess-1.4.3.0.a",
                  ],
                  version = "1.4.3.0",
                  deps = [
                    "//third-party-buck/gcc5/build/ghc:base",
                    "//third-party-buck/gcc5/build/ghc:__project__",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )

                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))

    @tests.utils.with_project()
    def test_haskell_external_library_parses_rts(self, root):
        buckfile = "third-party-buck/gcc5/build/ghc/BUCK"

        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
        haskell_external_library(
            name = "rts",
            db = "lib/package.conf.d",
            id = "rts",
            include_dirs = [
                "lib/include",
            ],
            lib_dir = "lib/rts",
            libs = ["HSrts_thr"],
            linker_flags = [
                "-u",
                "base_GHCziInt_I16zh_con_info",
                "-u",
                "base_GHCziInt_I32zh_con_info",
            ],
            version = "1.0",
            external_deps = [
                ("glibc", None, "m"),
                ("glibc", None, "rt"),
            ],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                haskell_prebuilt_library(
                  name = "rts",
                  cxx_header_dirs = [
                    "lib/include",
                  ],
                  db = "lib/package.conf.d",
                  exported_compiler_flags = [
                    "-expose-package",
                    "rts-1.0",
                  ],
                  exported_linker_flags = [
                    "-Wl,--no-as-needed",
                    "-Xlinker",
                    "-u",
                    "-Xlinker",
                    "base_GHCziInt_I16zh_con_info",
                    "-Xlinker",
                    "-u",
                    "-Xlinker",
                    "base_GHCziInt_I32zh_con_info",
                  ],
                  id = "rts",
                  shared_libs = {
                    "libHSrts_thr-ghc8.0.2.so": "lib/rts/libHSrts_thr-ghc8.0.2.so",
                  },
                  static_libs = [
                    "lib/rts/libHSrts_thr.a",
                  ],
                  version = "1.0",
                  deps = [
                    "//third-party-buck/gcc5/build/glibc:m",
                    "//third-party-buck/gcc5/build/glibc:rt",
                    "//third-party-buck/gcc5/build/ghc:__project__",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))

    @tests.utils.with_project()
    def test_haskell_external_library_handles_missing_id(self, root):
        package = "third-party-buck/gcc5/build/ghc"
        buckfile = os.path.join(package, "BUCK")
        root.addFile(
            os.path.join(package, "lib", "package.conf.d", "process-1.4.3.0-hash.conf"),
            "",
        )
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
        haskell_external_library(
            name = "process",
            db = "lib/package.conf.d",
            include_dirs = [
                "lib/process-1.4.3.0/include",
            ],
            lib_dir = "lib/process-1.4.3.0",
            libs = ["HSprocess-1.4.3.0"],
            version = "1.4.3.0",
            external_deps = [
                ("ghc", None, "base"),
            ],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                haskell_prebuilt_library(
                  name = "process",
                  cxx_header_dirs = [
                    "lib/process-1.4.3.0/include",
                  ],
                  db = "lib/package.conf.d",
                  exported_compiler_flags = [
                    "-expose-package",
                    "process-1.4.3.0",
                  ],
                  exported_linker_flags = [
                    "-Wl,--no-as-needed",
                  ],
                  id = "process-1.4.3.0-hash",
                  profiled_static_libs = [
                    "lib/process-1.4.3.0/libHSprocess-1.4.3.0_p.a",
                  ],
                  shared_libs = {
                    "libHSprocess-1.4.3.0-ghc8.0.2.so": "lib/process-1.4.3.0/libHSprocess-1.4.3.0-ghc8.0.2.so",
                  },
                  static_libs = [
                    "lib/process-1.4.3.0/libHSprocess-1.4.3.0.a",
                  ],
                  version = "1.4.3.0",
                  deps = [
                    "//third-party-buck/gcc5/build/ghc:base",
                    "//third-party-buck/gcc5/build/ghc:__project__",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )

                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))

    @tests.utils.with_project()
    def test_haskell_external_library_fails_on_missing_id(self, root):
        buckfile = "third-party-buck/gcc5/build/ghc/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
        haskell_external_library(
            name = "process",
            db = "lib/package.conf.d",
            include_dirs = [
                "lib/process-1.4.3.0/include",
            ],
            lib_dir = "lib/process-1.4.3.0",
            libs = ["HSprocess-1.4.3.0"],
            version = "1.4.3.0",
            external_deps = [
                ("ghc", None, "base"),
            ],
        )
        """
            ),
        )

        self.assertFailureWithMessage(
            root.runAudit([buckfile]), "cannot lookup package identifier"
        )
