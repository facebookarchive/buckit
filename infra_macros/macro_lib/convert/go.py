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
import os

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))


VENDOR_PATH = 'third-party-source/go'


def to_pascal_case(s):
    """
    Converts snake_case to PascalCase
    """
    parts = s.split('_')
    return ''.join([x.title() for x in parts])


class GoConverter(base.Converter):
    def __init__(self, context, rule_type, buck_rule_type=None):
        super(GoConverter, self).__init__(context)
        self._rule_type = rule_type
        self._buck_rule_type = buck_rule_type or rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def is_binary(self):
        return self.get_fbconfig_rule_type() in \
            ('go_binary', 'go_unittest',)

    def convert(
        self,
        base_path,
        name=None,
        srcs=None,
        gen_srcs=None,
        deps=None,
        exported_deps=None,
        go_external_deps=None,
        go_version=None,
        package_name=None,
        library=None,
        tests=None,
        compiler_flags=None,
        linker_flags=None,
    ):
        if srcs is None:
            srcs = []
        if gen_srcs is None:
            gen_srcs = []
        if deps is None:
            deps = []
        if go_external_deps is None:
            go_external_deps = []
        if compiler_flags is None:
            compiler_flags = []
        if linker_flags is None:
            linker_flags = []

        extra_rules = []

        attributes = collections.OrderedDict(
            name=name,
            srcs=self.convert_source_list(base_path, srcs + gen_srcs),
        )

        if tests:
            attributes['tests'] = []
            for test in tests:
                attributes['tests'].append(self.convert_build_target(base_path, test))

        if package_name:
            attributes['package_name'] = package_name

        if library:
            attributes['library'] = self.convert_build_target(base_path, library)

        dependencies = []
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))

        if self.is_binary():
            attributes['linker_flags'] = linker_flags

        for ext_dep in go_external_deps:
            # We used to allow a version hash to be specified for a dep inside
            # a tuple.  If it exists just ignore it.
            if base.is_collection(ext_dep):
                (ext_dep, _) = ext_dep
            dependencies.append("//{}/{}:{}".format(
                VENDOR_PATH, ext_dep, os.path.basename(ext_dep)
            ))
        attributes['deps'] = dependencies
        attributes['compiler_flags'] = compiler_flags

        if exported_deps:
            exported_deps = [self.convert_build_target(base_path, d)
                             for d in exported_deps]
            attributes['exported_deps'] = exported_deps

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules
