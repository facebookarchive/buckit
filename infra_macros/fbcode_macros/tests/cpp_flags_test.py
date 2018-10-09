# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class CppFlagsTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")]

    @tests.utils.with_project()
    def test_get_extra_flags_methods(self, root):
        root.updateBuckconfig("cxx", "extra_cflags", "-DCFLAG1 -DCFLAG2='true value'")
        root.updateBuckconfig(
            "cxx", "extra_cxxflags", "-DCXXFLAG1 -DCXXFLAG2='true value'"
        )
        root.updateBuckconfig(
            "cxx", "extra_cppflags", "-DCPPFLAG1 -DCPPFLAG2='true value'"
        )
        root.updateBuckconfig(
            "cxx", "extra_cxxppflags", "-DCXXPPFLAG1 -DCXXPPFLAG2='true value'"
        )
        root.updateBuckconfig(
            "cxx", "extra_ldflags", "-DLDFLAG1 -DLDFLAG2='true value'"
        )

        commands = [
            "cpp_flags.get_extra_cflags()",
            "cpp_flags.get_extra_cxxflags()",
            "cpp_flags.get_extra_cppflags()",
            "cpp_flags.get_extra_cxxppflags()",
            "cpp_flags.get_extra_ldflags()",
        ]
        expected = [
            ["-DCFLAG1", "-DCFLAG2=true value"],
            ["-DCXXFLAG1", "-DCXXFLAG2=true value"],
            ["-DCPPFLAG1", "-DCPPFLAG2=true value"],
            ["-DCXXPPFLAG1", "-DCXXPPFLAG2=true value"],
            ["-DLDFLAG1", "-DLDFLAG2=true value"],
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
