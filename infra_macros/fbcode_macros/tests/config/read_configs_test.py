# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class ReadConfigsTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/config:read_configs.bzl", "read_choice")]

    @tests.utils.with_project()
    def test_read_choice(self, root):
        root.updateBuckconfig("config", "value", "foo")
        expected = ["foo", "bar"]

        statements = [
            "read_choice('config', 'value', ('foo', 'bar'), 'bar')",
            "read_choice('config', 'does_not_exist', ('foo', 'bar'), 'bar')",
        ]

        ret = root.runUnitTests(self.includes, statements)

        self.assertSuccess(ret)
        self.assertEqual(expected, ret.debug_lines)
