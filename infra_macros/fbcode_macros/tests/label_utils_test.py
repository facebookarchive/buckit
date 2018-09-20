# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import platform

import tests.utils


class LabelsTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")]

    @tests.utils.with_project()
    def test_get_sanitizer(self, root):
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        expected1 = ["buck", "dev", "gcc", "gcc7", platform.machine(), "bar"]

        expected2 = ["buck", "dev", "gcc", "gcc7", platform.machine(), "bar", "asan"]

        self.assertSuccess(
            root.runUnitTests(
                self.includes, ['label_utils.convert_labels("gcc7", "bar")']
            ),
            expected1,
        )

        root.updateBuckconfig("fbcode", "sanitizer", "address")
        self.assertSuccess(
            root.runUnitTests(
                self.includes, ['label_utils.convert_labels("gcc7", "bar")']
            ),
            expected2,
        )
