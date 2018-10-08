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
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")


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
            nodefaultlibs=False,
        ):

        extra_rules = []
        dependencies = []
        platform = self.get_platform(base_path)

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['srcs'] = self.convert_source_list(base_path, srcs)

        if warnings_flags:
            attributes['warnings_flags'] = warnings_flags

        attributes['compiler_flags'] = ['-warn-error', '+a', '-safe-string']
        if compiler_flags:
            attributes['compiler_flags'].extend(
                self.convert_args_with_macros(
                    base_path,
                    compiler_flags,
                    platform=platform))

        attributes['ocamldep_flags'] = []
        if ocamldep_flags:
            attributes['ocamldep_flags'].extend(ocamldep_flags)

        if ppx_flag is not None:
            attributes['compiler_flags'].extend(['-ppx', ppx_flag])
            attributes['ocamldep_flags'].extend(['-ppx', ppx_flag])

        if not native:
            attributes['bytecode_only'] = True

        if self.get_fbconfig_rule_type() == 'ocaml_binary':
            attributes['platform'] = platform_utils.get_buck_platform_for_base_path(base_path)

        # Add the C/C++ build info lib to deps.
        if self.get_fbconfig_rule_type() == 'ocaml_binary':
            cxx_build_info, cxx_build_info_rules = (
                self.create_cxx_build_info_rule(
                    base_path,
                    name,
                    self.get_fbconfig_rule_type(),
                    platform,
                    visibility=visibility))
            dependencies.append(cxx_build_info)
            extra_rules.extend(cxx_build_info_rules)

        # Translate dependencies.
        for dep in deps:
            dependencies.append(target.parse_target(dep, base_path=base_path))

        # Translate external dependencies.
        for dep in external_deps:
            dependencies.append(self.normalize_external_dep(dep))

        # Add in binary-specific link deps.
        if self.is_binary():
            d, r = self.get_binary_link_deps(
                base_path,
                name,
                default_deps=not nodefaultlibs,
            )
            dependencies.extend(d)
            extra_rules.extend(r)

        # If any deps were specified, add them to the output attrs.
        if dependencies:
            attributes['deps'], attributes['platform_deps'] = (
                self.format_all_deps(dependencies))

        # Translate visibility
        if visibility is not None:
            attributes['visibility'] = visibility

        platform = self.get_platform(base_path)

        ldflags = self.get_ldflags(
            base_path,
            name,
            self.get_fbconfig_rule_type(),
            binary=self.is_binary(),
            platform=platform if self.is_binary() else None)

        if nodefaultlibs:
            ldflags.append('-nodefaultlibs')

        if "-flto" in ldflags:
            attributes['compiler_flags'].extend(["-ccopt", "-flto", "-cclib", "-flto"])
        if "-flto=thin" in ldflags:
            attributes['compiler_flags'].extend(["-ccopt", "-flto=thin", "-cclib", "-flto=thin"])

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules
