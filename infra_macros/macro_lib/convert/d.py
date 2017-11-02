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
load("{}:fbcode_target.py".format(macro_root),
     "RootRuleTarget",
     "RuleTarget",
     "ThirdPartyRuleTarget")


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

    def convert(self,
                base_path,
                name=None,
                srcs=[],
                deps=[],
                tags=(),
                linker_flags=(),
                external_deps=(),
                **kwargs):

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['srcs'] = srcs

        if self.is_test(self.get_buck_rule_type()):
            attributes['labels'] = self.convert_labels('d', *tags)

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
                platform=self.get_default_platform()))
        attributes['linker_flags'] = out_ldflags

        dependencies = []
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))
        for target in external_deps:
            dependencies.append(self.convert_external_build_target(target))
        # All D rules get an implicit dep on the runtime.
        dependencies.append(
            self.get_dep_target(
                ThirdPartyRuleTarget('dlang', 'druntime')))
        dependencies.append(
            self.get_dep_target(ThirdPartyRuleTarget('dlang', 'phobos')))
        # Add in binary-specific link deps.
        if self.is_binary():
            dependencies.extend(self.format_deps(self.get_binary_link_deps()))
        attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
