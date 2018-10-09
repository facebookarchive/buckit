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
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")


class DConverter(base.Converter):

    def __init__(self, context, rule_type, buck_rule_type=None):
        super(DConverter, self).__init__(context)
        self._rule_type = rule_type
        self._buck_rule_type = buck_rule_type or rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def is_binary(self):
        return self.get_fbconfig_rule_type() in ('d_binary', 'd_unittest')

    def _get_platform(self):
        return self._context.buck_ops.read_config('d', 'platform', None)

    def convert(self,
                base_path,
                name=None,
                srcs=[],
                deps=[],
                tags=(),
                linker_flags=(),
                external_deps=(),
                visibility=None,
                **kwargs):
        rules = []

        platform = self._get_platform()

        attributes = collections.OrderedDict()

        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility
        attributes['srcs'] = srcs

        if self.is_test(self.get_buck_rule_type()):
            attributes['labels'] = label_utils.convert_labels(platform, 'd', *tags)

        # Add in the base ldflags.
        out_ldflags = []
        out_ldflags.extend(linker_flags)
        out_ldflags.extend(
            self.get_ldflags(
                base_path,
                name,
                self.get_fbconfig_rule_type(),
                binary=self.is_binary(),
                build_info=self.is_binary(),
                platform=platform if self.is_binary() else None))
        attributes['linker_flags'] = out_ldflags

        dependencies = []
        for target in deps:
            dependencies.append(
                src_and_dep_helpers.convert_build_target(
                    base_path,
                    target,
                    platform=platform))
        for target in external_deps:
            dependencies.append(
                src_and_dep_helpers.convert_external_build_target(target, platform=platform))
        # All D rules get an implicit dep on the runtime.
        dependencies.append(
            target_utils.target_to_label(
                target_utils.ThirdPartyRuleTarget('dlang', 'druntime'),
                platform=platform))
        dependencies.append(
            target_utils.target_to_label(
                target_utils.ThirdPartyRuleTarget('dlang', 'phobos'),
                platform=platform))
        # Add in binary-specific link deps.
        if self.is_binary():
            d, r = self.get_binary_link_deps(
                base_path,
                name,
                attributes['linker_flags'])
            dependencies.extend(src_and_dep_helpers.format_deps(d, platform=platform))
            rules.extend(r)
        attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)] + rules
