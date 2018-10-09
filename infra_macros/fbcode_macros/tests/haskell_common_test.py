# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class HaskellCommonTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:haskell_common.bzl", "haskell_common")]

    @tests.utils.with_project()
    def test_reads_config_properly_using_defaults(self, root):
        commands = [
            "haskell_common.read_hs_debug()",
            "haskell_common.read_hs_eventlog()",
            "haskell_common.read_hs_profile()",
            "haskell_common.read_extra_ghc_compiler_flags()",
            "haskell_common.read_extra_ghc_linker_flags()",
        ]

        expected = [False, False, False, [], []]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_reads_config_properly(self, root):
        root.updateBuckconfigWithDict(
            {
                "fbcode": {
                    "hs_debug": "true",
                    "hs_eventlog": "true",
                    "hs_profile": "true",
                },
                "haskell": {
                    "extra_compiler_flags": "CFOO  CBAR",
                    "extra_linker_flags": "LFOO  LBAR",
                },
            }
        )
        commands = [
            "haskell_common.read_hs_debug()",
            "haskell_common.read_hs_eventlog()",
            "haskell_common.read_hs_profile()",
            "haskell_common.read_extra_ghc_compiler_flags()",
            "haskell_common.read_extra_ghc_linker_flags()",
        ]

        expected = [True, True, True, ["CFOO", "CBAR"], ["LFOO", "LBAR"]]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
