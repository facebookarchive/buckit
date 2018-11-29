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

        attributes = rust_common.convert_rust(
            name,
            self.get_fbconfig_rule_type(),
            srcs=srcs,
            deps=deps,
            rustc_flags=rustc_flags,
            features=features,
            crate=crate,
            link_style=link_style,
            preferred_linkage=preferred_linkage,
            visibility=visibility,
            external_deps=external_deps,
            crate_root=crate_root,
            linker_flags=linker_flags,
            framework=framework,
            unittests=unittests,
            proc_macro=proc_macro,
            tests=tests,
            test_features=test_features,
            test_rustc_flags=test_rustc_flags,
            test_link_style=test_link_style,
            test_linker_flags=test_linker_flags,
            test_srcs=test_srcs,
            test_deps=test_deps,
            test_external_deps=test_external_deps,
            allocator=allocator,
            **kwargs)

        return [Rule(self.get_buck_rule_type(), attributes)]
