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
import pipes
import os.path

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:rust_common.bzl", "rust_common")
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")


class RustConverter(base.Converter):
    def __init__(self, context, rule_type):
        super(RustConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        if self._rule_type == 'rust_unittest':
            return 'rust_test'
        else:
            return self._rule_type

    def is_binary(self):
        return self.get_fbconfig_rule_type() in \
            ('rust_binary', 'rust_unittest',)

    def is_test(self):
        return self.get_fbconfig_rule_type() in ('rust_unittest',)

    def is_deployable(self):
        return self.is_binary()

    def get_allowed_args(self):
        # common
        ok = set([
            'name',
            'srcs',
            'deps',
            'external_deps',
            'features',
            'rustc_flags',
            'crate',
            'crate_root',
        ])

        # non-tests
        if not self.is_test():
            ok |= set([
                'unittests',
                'tests',
                'test_deps',
                'test_external_deps',
                'test_srcs',
                'test_features',
                'test_rustc_flags',
                'test_link_style',
            ])
        else:
            ok.update(['framework'])

        # linkable
        if self.is_binary():
            ok |= set(['linker_flags', 'link_style', 'allocator'])
        else:
            ok |= set(['preferred_linkage', 'proc_macro'])

        return ok

    def convert(self,
                base_path,
                name,
                srcs=None,
                deps=None,
                rustc_flags=None,
                features=None,
                crate=None,
                link_style=None,
                preferred_linkage=None,
                visibility=None,
                external_deps=None,
                crate_root=None,
                linker_flags=None,
                framework=True,
                unittests=True,
                proc_macro=False,
                tests=None,
                test_features=None,
                test_rustc_flags=None,
                test_link_style=None,
                test_linker_flags=None,
                test_srcs=None,
                test_deps=None,
                test_external_deps=None,
                allocator=None,
                **kwargs):

        extra_rules = []
        dependencies = []

        attributes = collections.OrderedDict()

        attributes['name'] = name
        attributes['srcs'] = src_and_dep_helpers.convert_source_list(base_path, srcs or [])
        attributes['features'] = features or []

        if not crate_root and not self.is_test():
            # Compute a crate_root if one wasn't specified. We'll need this
            # to pass onto the generated test rule.
            topsrc_options = ((crate or name) + '.rs',)
            if self.get_fbconfig_rule_type() == 'rust_binary':
                topsrc_options += ('main.rs',)
            if self.get_fbconfig_rule_type() == 'rust_library':
                topsrc_options += ('lib.rs',)

            topsrc = []
            for s in srcs or []:
                if s.startswith(':'):
                    continue
                if os.path.basename(s) in topsrc_options:
                    topsrc.append(s)

            # Not sure what to do about too many or not enough crate roots
            if len(topsrc) == 1:
                crate_root = topsrc[0]

        if crate_root:
            attributes['crate_root'] = crate_root

        if rustc_flags:
            attributes['rustc_flags'] = rustc_flags

        if crate:
            attributes['crate'] = crate

        attributes['default_platform'] = platform_utils.get_buck_platform_for_base_path(base_path)

        if self.is_binary():
            platform = platform_utils.get_platform_for_base_path(base_path)
            if not link_style:
                link_style = cpp_common.get_link_style()

            attributes['link_style'] = link_style

            ldflags = cpp_common.get_ldflags(
                base_path,
                name,
                self.get_fbconfig_rule_type(),
                binary=True,
                build_info=True,
                platform=platform)
            attributes['linker_flags'] = ldflags + (linker_flags or [])

            # Add the Rust build info lib to deps.
            rust_build_info = (
                rust_common.create_rust_build_info_rule(
                    base_path,
                    name,
                    crate,
                    self.get_fbconfig_rule_type(),
                    platform,
                    visibility))
            dependencies.append(rust_build_info)

        else:
            if proc_macro:
                attributes['proc_macro'] = proc_macro

            if preferred_linkage:
                attributes['preferred_linkage'] = preferred_linkage

        if rustc_flags:
            attributes['rustc_flags'] = rustc_flags

        if visibility:
            attributes['visibility'] = visibility

        # Translate dependencies.
        for dep in deps or []:
            dependencies.append(target_utils.parse_target(dep, default_base_path=base_path))

        # Translate external dependencies.
        for dep in external_deps or []:
            dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

        if not tests:
            tests = []

        # Add test rule for all library/binary rules
        # It has the same set of srcs and dependencies as the base rule,
        # but also allows additional test srcs, deps and external deps.
        # test_features and test_rustc_flags override the base rule keys,
        # if present.
        if not self.is_test() and unittests:
            test_name = rust_common.create_rust_test_rule(
                self.get_fbconfig_rule_type(),
                base_path,
                dependencies,
                attributes,
                test_srcs,
                test_deps,
                test_external_deps,
                test_rustc_flags,
                test_features,
                test_link_style,
                test_linker_flags,
                allocator,
                visibility,
            )
            tests.append(':' + test_name)
            attributes['tests'] = tests

        if self.is_test():
            attributes['framework'] = framework

        # Add in binary-specific link deps.
        # Do this after creating the test rule, so that it doesn't pick this
        # up as well (it will add its own binary deps as needed)
        if self.is_binary():
            d = rust_common.get_rust_binary_deps(
                base_path,
                name,
                linker_flags,
                allocator,
            )
            dependencies.extend(d)

        # If any deps were specified, add them to the output attrs.
        if dependencies:
            attributes['deps'], attributes['platform_deps'] = (
                src_and_dep_helpers.format_all_deps(dependencies))

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules
