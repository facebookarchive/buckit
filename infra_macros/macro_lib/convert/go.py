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


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


base = import_macro_lib('convert/base')
Rule = import_macro_lib('rule').Rule
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")

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

    def is_cgo(self):
        return self.get_fbconfig_rule_type() in ['cgo_library', 'go_bindgen_library']

    def is_test(self):
        return self.get_fbconfig_rule_type() == 'go_unittest'

    def convert(
        self,
        base_path,
        name=None,
        srcs=None,
        go_srcs=None,
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
        external_linker_flags=None,
        coverage_mode=None,
        resources=None,

        # special purpose flag, appends the facebook specific c++ libs to the
        # go binary (ex. sanitizers)
        cgo=False,

        # cgo
        headers=None,
        preprocessor_flags=None,
        cgo_compiler_flags=None,
        linker_extra_outputs=None,
        link_style=None,
        visibility=None,
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
        if external_linker_flags is None:
            external_linker_flags = []
        if resources is None:
            resources = []

        # cgo attributes
        if go_srcs is None:
            go_srcs = []
        if headers is None:
            headers = []
        if preprocessor_flags is None:
            preprocessor_flags = []
        if cgo_compiler_flags is None:
            cgo_compiler_flags = []
        if linker_extra_outputs is None:
            linker_extra_outputs = []

        extra_rules = []

        attributes = collections.OrderedDict(
            name=name,
            srcs=self.convert_source_list(base_path, srcs + gen_srcs),
        )

        if visibility is not None:
            attributes['visibility'] = visibility

        if tests:
            attributes['tests'] = []
            for test in tests:
                attributes['tests'].append(self.convert_build_target(base_path, test))

        if package_name:
            attributes['package_name'] = package_name

        if library:
            attributes['library'] = self.convert_build_target(base_path, library)

        if resources:
            attributes['resources'] = resources

        if self.is_binary():
            attributes['platform'] = platform_utils.get_buck_platform_for_base_path(base_path)

        dependencies = []
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))

        if self.is_binary() or (self.is_cgo() and linker_flags):
            attributes['linker_flags'] = linker_flags

        if self.is_binary() or (self.is_cgo() and external_linker_flags):
            attributes['external_linker_flags'] = external_linker_flags

        if self.is_cgo() and link_style == None:
            link_style = self.get_link_style()

        if (self.is_binary() or self.is_test()) and cgo == True:
            if link_style == None:
                link_style = self.get_link_style()

            attributes['linker_flags'] = linker_flags
            d, r = self.get_binary_link_deps(
                base_path,
                name,
                attributes['linker_flags'] if 'linker_flags' in attributes else [],
            )

            formatted_deps = self.format_deps(
                d,
                platform=platform_utils.get_buck_platform_for_base_path(
                    base_path
                )
            )

            r.append(Rule('genrule', {
                'name' : 'gen-asan-lib',
                'cmd' : 'echo \'package asan\nimport "C"\' > $OUT',
                'out' : 'asan.go',
            }))

            r.append(Rule('cgo_library', {
                'name' : 'cgo-asan-lib',
                'package_name' : 'asan',
                'srcs' : [':gen-asan-lib'],
                'deps' : formatted_deps,
                'link_style' : link_style,
            }))

            dependencies.append(":cgo-asan-lib")
            extra_rules.extend(r)

        if self.is_test():
            # add benchmark rule to targets
            extra_rules.append(Rule('command_alias', {
                'name': name + "-bench",
                'exe': ":" + name,
                'args': [
                    '-test.bench=.',
                    '-test.benchmem',
                ],
            }))

        for ext_dep in go_external_deps:
            # We used to allow a version hash to be specified for a dep inside
            # a tuple.  If it exists just ignore it.
            if base.is_collection(ext_dep):
                (ext_dep, _) = ext_dep
            dependencies.append("//{}/{}:{}".format(
                VENDOR_PATH, ext_dep, os.path.basename(ext_dep)
            ))
        attributes['deps'] = dependencies
        if compiler_flags:
            attributes['compiler_flags'] = compiler_flags

        if exported_deps:
            exported_deps = [self.convert_build_target(base_path, d)
                             for d in exported_deps]
            attributes['exported_deps'] = exported_deps

        # cgo options (those should ~copy-pasta from cxx_binary rule)
        if go_srcs:
            attributes['go_srcs'] = go_srcs
        if headers:
            attributes['headers'] = headers
        if preprocessor_flags:
            attributes['preprocessor_flags'] = preprocessor_flags
        if cgo_compiler_flags:
            attributes['cgo_compiler_flags'] = cgo_compiler_flags
        if linker_extra_outputs:
            attributes['linker_extra_outputs'] = linker_extra_outputs
        if link_style:
            attributes['link_style'] = link_style

        if self.is_test():
            attributes['coverage_mode'] = "set"

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules
