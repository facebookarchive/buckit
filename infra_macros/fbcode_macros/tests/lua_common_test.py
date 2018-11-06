# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class LuaCommonTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:lua_common.bzl", "lua_common")]

    @tests.utils.with_project()
    def test_get_lua_base_module(self, root):
        commands = [
            'lua_common.get_lua_base_module("foo/bar", None)',
            'lua_common.get_lua_base_module("foo/bar", "")',
            'lua_common.get_lua_base_module("foo/bar", "something.else")',
        ]
        expected = ["fbcode.foo.bar", "", "something.else"]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_get_lua_init_symbol(self, root):
        commands = [
            'lua_common.get_lua_init_symbol("foo/bar", "baz", None)',
            'lua_common.get_lua_init_symbol("foo/bar", "baz", "")',
            'lua_common.get_lua_init_symbol("foo/bar", "baz", "something.else")',
        ]
        expected = [
            "luaopen_fbcode_foo_bar_baz",
            "luaopen_baz",
            "luaopen_something_else_baz",
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
