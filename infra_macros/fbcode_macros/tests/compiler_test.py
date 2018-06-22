# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import tests.utils


class CompilerTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:compiler.bzl", "compiler")]

    @tests.utils.with_project()
    def test_require_global_compiler_no_global_compiler(self, root):
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes,
                ['compiler.require_global_compiler("ERROR")']),
            "ERROR")

    @tests.utils.with_project()
    def test_require_global_compiler_wrong_global_compiler(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes,
                ['compiler.require_global_compiler("ERROR", "clang")']),
            "ERROR")

    @tests.utils.with_project()
    def test_require_global_compiler_any_compiler(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                ['compiler.require_global_compiler("ERROR")']),
            None)

    @tests.utils.with_project()
    def test_require_global_compiler_specific_compiler(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                ['compiler.require_global_compiler("ERROR", "gcc")']),
            None)
