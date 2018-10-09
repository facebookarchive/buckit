# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class CoverageTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:coverage.bzl", "coverage")]

    @tests.utils.with_project(run_buckd=True)
    def test_get_coverage_ldflags(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "clang")

        commands = ['coverage.get_coverage_ldflags("foo/bar")']

        # Coverage enabled, no sanitizer
        root.updateBuckconfig("fbcode", "coverage", True)
        expected = ["-fprofile-instr-generate", "-fcoverage-mapping"]

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage enabled, no sanitizer, enabled by path as well
        root.updateBuckconfig("cxx", "coverage_only", "foo/bar something/other")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        expected = []

        # Coverage enabled, sanitizer
        root.updateBuckconfig("fbcode", "sanitizer", "something")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage disabled by path, no sanitizer
        root.updateBuckconfig("fbcode", "sanitizer", "")
        root.updateBuckconfig("cxx", "coverage_only", "foo/bar/baz something/other")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage disabled, no sanitizer
        root.updateBuckconfig("fbcode", "coverage", "false")
        root.updateBuckconfig("cxx", "coverage_only", "foo/bar something/other")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Non-clang
        root.updateBuckconfig("fbcode", "coverage", "true")
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")

        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands), "use clang globally"
        )

    @tests.utils.with_project(run_buckd=True)
    def test_get_coverage_flags(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "clang")

        commands = ['coverage.get_coverage_flags("foo/bar")']

        # Coverage enabled, no sanitizer
        root.updateBuckconfig("fbcode", "coverage", True)
        expected = ["-fprofile-instr-generate", "-fcoverage-mapping"]

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage enabled, no sanitizer, enabled by path as well
        root.updateBuckconfig("cxx", "coverage_only", "foo/bar something/other")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage enabled, sanitizer
        root.updateBuckconfig("fbcode", "sanitizer", "something")

        expected = ["-fsanitize-coverage=bb"]

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        expected = []

        # Coverage disabled by path, no sanitizer
        root.updateBuckconfig("fbcode", "sanitizer", "")
        root.updateBuckconfig("cxx", "coverage_only", "foo/bar/baz something/other")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage disabled, no sanitizer
        root.updateBuckconfig("fbcode", "coverage", "false")
        root.updateBuckconfig("cxx", "coverage_only", "foo/bar something/other")

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Non-clang
        root.updateBuckconfig("fbcode", "coverage", "true")
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")

        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands), "use clang globally"
        )

    @tests.utils.with_project(run_buckd=True)
    def test_get_coverage_binary_deps(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "clang")

        commands = ["coverage.get_coverage_binary_deps()"]

        # Coverage enabled, no sanitizer
        root.updateBuckconfig("fbcode", "coverage", True)
        expected = [self.rule_target("third-party", "llvm-fb", "clang_rt.profile")]

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage enabled, sanitizer
        root.updateBuckconfig("fbcode", "sanitizer", "something")
        expected = []

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

        # Coverage disabled
        root.updateBuckconfig("fbcode", "coverage", "false")

        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands), "fbcode.coverage is false"
        )

        # Non-clang
        root.updateBuckconfig("fbcode", "coverage", "true")
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")

        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands), "use clang globally"
        )
