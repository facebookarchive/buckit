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


class SrcAndDepHelpersTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")]

    @tests.utils.with_project()
    def test_get_source_name_works(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    'src_and_dep_helpers.get_source_name("//foo/bar:baz=path/to/baz1.cpp")',
                    'src_and_dep_helpers.get_source_name(":baz=path/to/baz2.cpp")',
                    'src_and_dep_helpers.get_source_name("path/to/baz3.cpp")',
                ],
            ),
            'path/to/baz1.cpp',
            'path/to/baz2.cpp',
            'path/to/baz3.cpp',
        )

    @tests.utils.with_project()
    def test_get_source_name_fails_if_no_equals_sign(self, root):
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes,
                [
                    'src_and_dep_helpers.get_source_name("//foo:bar")',
                ],
            ),
            "generated source target //foo:bar is missing `=<name>` suffix",
        )
