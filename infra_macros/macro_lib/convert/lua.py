#!/usr/bin/env python2

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

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:lua_binary.bzl", "lua_binary")
load("@fbcode_macros//build_defs:lua_library.bzl", "lua_library")
load("@fbcode_macros//build_defs/lib:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")


class LuaConverter(base.Converter):

    def __init__(self, context, rule_type, buck_rule_type=None):
        super(LuaConverter, self).__init__(context)
        self._rule_type = rule_type
        self._buck_rule_type = buck_rule_type or rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def is_test(self):
        return self.get_fbconfig_rule_type() == 'lua_unittest'

    def get_base_module(self, base_path, base_module=None):
        if base_module is None:
            return paths.join('fbcode', base_path)
        return base_module

    def get_module_name(self, name, explicit_name=None):
        if explicit_name is None:
            return name
        return explicit_name

    def convert_unittest(
            self,
            base_path,
            name=None,
            tags=(),
            type='lua',
            visibility=None,
            **kwargs):
        """
        Buckify a unittest rule.
        """
        # Generate the test binary rule and fixup the name.
        binary_name = name + '-binary'
        lua_binary(
            name=name,
            binary_name=binary_name,
            package_style='inplace',
            visibility=visibility,
            is_test=True,
            **kwargs)

        # Create a `sh_test` rule to wrap the test binary and set it's tags so
        # that testpilot knows it's a lua test.
        platform = platform_utils.get_platform_for_base_path(base_path)
        fb_native.sh_test(
            name=name,
            visibility=get_visibility(visibility, name),
            test=':' + binary_name,
            labels=(
                label_utils.convert_labels(platform, 'lua', 'custom-type-' + type, *tags)),
        )

    def convert(self, base_path, *args, **kwargs):
        rtype = self.get_fbconfig_rule_type()
        if rtype == 'lua_library':
            lua_library(*args, **kwargs)
        elif rtype == 'lua_binary':
            lua_binary(*args, **kwargs)
        elif rtype == 'lua_unittest':
            self.convert_unittest(base_path, *args, **kwargs)
        else:
            raise Exception('unexpected type: ' + rtype)
        return []
