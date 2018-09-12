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

import platform
import tests.utils


class SanitizersTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")]

    @tests.utils.with_project()
    def test_get_sanitizer(self, root):
        self.assertSuccess(
            root.runUnitTests(self.includes, ["sanitizers.get_sanitizer()"]), None
        )

        root.updateBuckconfig("fbcode", "sanitizer", "address")
        if platform.machine() == "aarch64":
            expected = None
        else:
            expected = "address"

        self.assertSuccess(
            root.runUnitTests(self.includes, ["sanitizers.get_sanitizer()"]), expected
        )

    @tests.utils.with_project()
    def test_get_sanitizer_deps(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes, ["sanitizers.get_sanitizer_binary_deps()"]
            ),
            [],
        )

        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        root.updateBuckconfig("fbcode", "sanitizer", "address")
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ["sanitizers.get_sanitizer_binary_deps()"]
            ),
            "can only use sanitizers with build modes that use clang globally",
        )

        root.updateBuckconfig("fbcode", "global_compiler", "clang")
        self.assertSuccess(
            root.runUnitTests(
                self.includes, ["sanitizers.get_sanitizer_binary_deps()"]
            ),
            [("tools/build/sanitizers", "asan-cpp")],
        )

    @tests.utils.with_project()
    def test_get_sanitizer_flags(self, root):
        expected_flags = [
            "-fsanitize=thread",
            "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer",
        ]

        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, ["sanitizers.get_sanitizer_flags()"]),
            "No sanitizer was specified",
        )

        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        root.updateBuckconfig("fbcode", "sanitizer", "thread")
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, ["sanitizers.get_sanitizer_flags()"]),
            "can only use sanitizers with build modes that use clang globally",
        )

        root.updateBuckconfig("fbcode", "global_compiler", "clang")
        root.updateBuckconfig("fbcode", "sanitizer", "invalid-sanitizer")
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, ["sanitizers.get_sanitizer_flags()"]),
            "No flags are available for sanitizer invalid-sanitizer",
        )

        root.updateBuckconfig("fbcode", "sanitizer", "thread")
        self.assertSuccess(
            root.runUnitTests(self.includes, ["sanitizers.get_sanitizer_flags()"]),
            expected_flags,
        )

    @tests.utils.with_project()
    def test_get_sanitizer_label(self, root):
        self.assertSuccess(
            root.runUnitTests(self.includes, ["sanitizers.get_label()"]), None
        )

        root.updateBuckconfig("fbcode", "sanitizer", "address-undefined-dev")
        self.assertSuccess(
            root.runUnitTests(self.includes, ["sanitizers.get_label()"]), None
        )

        root.updateBuckconfig("fbcode", "sanitizer", "address")
        self.assertSuccess(
            root.runUnitTests(self.includes, ["sanitizers.get_label()"]), "asan"
        )

    @tests.utils.with_project()
    def test_get_short_name(self, root):
        self.assertSuccess(
            root.runUnitTests(self.includes, ['sanitizers.get_short_name("address")']),
            "asan",
        )
