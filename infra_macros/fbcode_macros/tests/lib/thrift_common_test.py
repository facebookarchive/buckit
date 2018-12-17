# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class ThriftCommonTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")]

    @tests.utils.with_project()
    def test_merge_sources_map(self, root):
        commands = [
            (
                "thrift_common.merge_sources_map({"
                '"foo.thrift": {'
                '"gen-cpp2/foo_data.h": "//foo:if=gen-cpp2/foo_data.h",'
                '"gen-cpp2/FooService.h": "//foo:if=gen-cpp2/FooService.h",'
                "},"
                '"bar.thrift": {'
                '"gen-cpp2/bar_data.h": "//bar:if=gen-cpp2/bar_data.h",'
                '"gen-cpp2/BarService.h": "//bar:if=gen-cpp2/BarService.h",'
                "},"
                "})"
            )
        ]

        expected = {
            "gen-cpp2/foo_data.h": "//foo:if=gen-cpp2/foo_data.h",
            "gen-cpp2/FooService.h": "//foo:if=gen-cpp2/FooService.h",
            "gen-cpp2/bar_data.h": "//bar:if=gen-cpp2/bar_data.h",
            "gen-cpp2/BarService.h": "//bar:if=gen-cpp2/BarService.h",
        }

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)
