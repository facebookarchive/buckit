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
include_defs("{}/fbcode_target.py".format(macro_root), "target")
include_defs("{}/rule.py".format(macro_root))

load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

class RustLibraryExternalConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'rust_external_library'

    def get_buck_rule_type(self):
        return 'prebuilt_rust_library'

    def convert(self,
                base_path,
                name=None,
                rlib=None,
                crate=None,
                deps=(),
                licenses=(),
                visibility=None,
                external_deps=()):

        platform = self.get_tp2_build_dat(base_path)['platform']

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['rlib'] = rlib

        if crate:
            attributes['crate'] = crate

        if licenses:
            attributes['licenses'] = licenses

        if visibility:
            attributes['visibility'] = visibility

        dependencies = []
        for dep in deps:
            dependencies.append(target_utils.parse_target(dep, default_base_path=base_path))
        for dep in external_deps:
            dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))
        if dependencies:
            attributes['deps'] = (
                src_and_dep_helpers.format_deps(dependencies, platform=platform))

        return [Rule(self.get_buck_rule_type(), attributes)]
