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

import collections

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@fbcode_macros//build_defs:d_common.bzl", "d_common")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")


class DConverter(base.Converter):

    def __init__(self, context, rule_type, buck_rule_type=None):
        super(DConverter, self).__init__(context)
        self._rule_type = rule_type
        self._buck_rule_type = buck_rule_type or rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def convert(self,
                base_path,
                name,
                is_binary,
                d_rule_type,
                srcs=[],
                deps=[],
                tags=None,
                linker_flags=(),
                external_deps=(),
                visibility=None,
                ):

        attributes = d_common.convert_d(
            name=name,
            is_binary=is_binary,
            d_rule_type=d_rule_type,
            srcs=srcs,
            deps=deps,
            tags=tags,
            linker_flags=linker_flags,
            external_deps=external_deps,
            visibility=visibility,
        )

        return [Rule(self.get_buck_rule_type(), attributes)]

class DBinaryConverter(DConverter):
    def convert(
        self,
        base_path,
        name,
        srcs=(),
        deps=(),
        linker_flags=(),
        external_deps=(),
        visibility=None,
    ):
        return super(DBinaryConverter, self).convert(
            base_path=base_path,
            name=name,
            is_binary=True,
            d_rule_type='d_binary',
            srcs=srcs,
            deps=deps,
            linker_flags=linker_flags,
            external_deps=external_deps,
            visibility=visibility,
        )

class DLibraryConverter(DConverter):
    def convert(
        self,
        base_path,
        name,
        srcs=(),
        deps=(),
        linker_flags=(),
        external_deps=(),
        visibility=None,
    ):
        return super(DLibraryConverter, self).convert(
            base_path=base_path,
            name=name,
            is_binary=False,
            d_rule_type='d_library',
            srcs=srcs,
            deps=deps,
            linker_flags=linker_flags,
            external_deps=external_deps,
            visibility=visibility,
        )

class DUnitTestConverter(DConverter):
    def convert(
        self,
        base_path,
        name,
        srcs=(),
        deps=(),
        tags=(),
        linker_flags=(),
        external_deps=(),
        visibility=None,
    ):
        return super(DUnitTestConverter, self).convert(
            base_path=base_path,
            name=name,
            is_binary=True,
            d_rule_type='d_unittest',
            srcs=srcs,
            deps=deps,
            tags=tags,
            linker_flags=linker_flags,
            external_deps=external_deps,
            visibility=visibility,
        )
