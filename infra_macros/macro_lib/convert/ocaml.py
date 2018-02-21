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


class OCamlConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(OCamlConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._rule_type

    def is_binary(self):
        return self.get_fbconfig_rule_type() in ('ocaml_binary',)

    def convert(
            self,
            base_path,
            name=None,
            srcs=(),
            deps=(),
            compiler_flags=None,
            ocamldep_flags=None,
            native=True,
            warnings_flags=None,
            supports_coverage=None,
            external_deps=(),
            visibility=None,
            ppx_flag=None,
        ):

        extra_rules = []
        dependencies = []

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['srcs'] = self.convert_source_list(base_path, srcs)

        if warnings_flags:
            attributes['warnings_flags'] = warnings_flags

        attributes['compiler_flags'] = ['-warn-error', '+a']
        if compiler_flags:
            attributes['compiler_flags'].extend(
                self.convert_args_with_macros(
                    base_path,
                    compiler_flags,
                    platform=self.get_default_platform()))

        attributes['ocamldep_flags'] = []
        if ocamldep_flags:
            attributes['ocamldep_flags'].extend(ocamldep_flags)

        if ppx_flag is not None:
            attributes['compiler_flags'].extend(['-ppx', ppx_flag])
            attributes['ocamldep_flags'].extend(['-ppx', ppx_flag])

        if not native:
            attributes['bytecode_only'] = True

        # Add the C/C++ build info lib to deps.
        if self.get_fbconfig_rule_type() == 'ocaml_binary':
            cxx_build_info, cxx_build_info_rules = (
                self.create_cxx_build_info_rule(
                    base_path,
                    name,
                    self.get_fbconfig_rule_type(),
                    self.get_default_platform()))
            dependencies.append(self.get_dep_target(cxx_build_info))
            extra_rules.extend(cxx_build_info_rules)

        # Translate dependencies.
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))

        # Translate external dependencies.
        for target in external_deps:
            dependencies.append(self.convert_external_build_target(target))

        # Add in binary-specific link deps.
        if self.is_binary():
            dependencies.extend(self.format_deps(self.get_binary_link_deps()))

        # If any deps were specified, add them to the output attrs.
        if dependencies:
            attributes['deps'] = dependencies

        # Translate visibility
        if visibility is not None:
            attributes['visibility'] = visibility

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules
