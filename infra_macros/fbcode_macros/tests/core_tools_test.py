# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CoreToolsTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")]

    @tests.utils.with_project()
    def test_returns_whether_in_set(self, root):
        root.project.cells["fbcode_macros"].writeFile(
            "build_defs/core_tools_targets.bzl",
            dedent(
                """
                load("@bazel_skylib//lib:new_sets.bzl", "sets")
                core_tools_targets = sets.make([
                    ("foo", "bar"),
                ])
                """
            ),
        )

        result = root.runUnitTests(
            self.includes,
            [
                'core_tools.is_core_tool(package_name(), "bar")',
                'core_tools.is_core_tool(package_name(), "baz")',
            ],
            buckfile="foo/BUCK",
        )
        self.assertSuccess(result, True, False)
