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
import pipes

from . import base
from ..rule import Rule

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

        # Add the Go buildinfo lib to deps.
        if self.is_binary():
            go_build_info, go_build_info_rules = (
                self.create_go_build_info_rule(
                    base_path,
                    name,
                    self.get_fbconfig_rule_type()))
            dependencies.append(go_build_info)
            extra_rules.extend(go_build_info_rules)
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

    def create_go_build_info_rule(
            self,
            base_path,
            name,
            rule_type):
        """
        Create rules to generate a Go library with build info.
        """
        rules = []

        info = (
            self.get_build_info(
                base_path,
                name,
                rule_type,
                self.get_default_platform()))
        info['go_root'] = self._context.buck_ops.read_config('go', 'root')

        template = "package buildinfo\n\nconst (\n"

        # Construct a template
        for k, v in info.items():
            k = to_pascal_case(k)

            if not isinstance(v, int):
                v = '"{}"'.format(v)

            template += "\t{} = {}\n".format(k, v)
        template += ")\n"

        # Setup a rule to generate the build info Rust file.
        source_name = name + "_gobuildinfo_gen"
        source_attrs = collections.OrderedDict()
        source_attrs['name'] = source_name
        source_attrs['out'] = 'buildinfo.go'
        source_attrs['cmd'] = (
            'mkdir -p `dirname $OUT` && echo {0} > $OUT'
            .format(pipes.quote(template)))
        rules.append(Rule('genrule', source_attrs))

        # Setup a rule to compile the build info C file into a library.
        lib_name = name + '_gobuildinfo'
        lib_attrs = collections.OrderedDict()
        lib_attrs['name'] = lib_name
        lib_attrs['package_name'] = "buildinfo"
        lib_attrs['srcs'] = [':' + source_name]
        rules.append(Rule('go_library', lib_attrs))

        return ':' + lib_name, rules
