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
import itertools
import re

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/cxx_sources.py".format(macro_root), "cxx_sources")
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:types.bzl", "types")
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:auto_pch_blacklist.bzl", "auto_pch_blacklist")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:auto_headers.bzl", "AutoHeaders", "get_auto_headers")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:build_mode.bzl", _build_mode="build_mode")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:haskell_common.bzl", "haskell_common")
load("@fbcode_macros//build_defs:lua_common.bzl", "lua_common")
load("@bazel_skylib//lib:partial.bzl", "partial")


class CppConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(CppConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        # Only kept for converter.py right now. Will be removed shortly
        return self._rule_type

    def convert_rule(
            self,
            base_path,
            name,
            cpp_rule_type,
            buck_rule_type,
            is_library,
            is_buck_binary,
            is_test,
            is_deployable,
            base_module=None,
            module_name=None,
            srcs=[],
            src=None,
            deps=[],
            arch_compiler_flags={},
            compiler_flags=(),
            known_warnings=[],
            headers=None,
            header_namespace=None,
            compiler_specific_flags={},
            supports_coverage=None,
            tags=(),
            linker_flags=(),
            arch_preprocessor_flags={},
            preprocessor_flags=(),
            prefix_header=None,
            precompiled_header=cpp_common.ABSENT_PARAM,
            propagated_pp_flags=(),
            link_whole=None,
            global_symbols=[],
            allocator=None,
            args=None,
            external_deps=[],
            type='gtest',
            owner=None,
            emails=None,
            dlopen_enabled=None,
            nodefaultlibs=False,
            shared_system_deps=None,
            system_include_paths=None,
            split_symbols=None,
            env=None,
            use_default_test_main=True,
            lib_name=None,
            nvcc_flags=(),
            hip_flags=(),
            enable_lto=False,
            hs_profile=None,
            dont_link_prerequisites=None,
            lex_args=(),
            yacc_args=(),
            runtime_files=(),
            additional_coverage_targets=(),
            py3_sensitive_deps=(),
            dlls={},
            versions=None,
            visibility=None,
            auto_headers=None,
            preferred_linkage=None,
            os_deps=None,
            os_linker_flags=None,
            autodeps_keep=False,
            undefined_symbols=False,
            modular_headers=None,
            modules=None,
            overridden_link_style=None,
            rule_specific_deps=None,
            rule_specific_preprocessor_flags=None,
            tests=None):
        attributes = cpp_common.convert_cpp(
            name,
            cpp_rule_type,
            buck_rule_type,
            is_library,
            is_buck_binary,
            is_test,
            is_deployable,
            base_module=base_module,
            module_name=module_name,
            srcs=srcs,
            src=src,
            deps=deps,
            arch_compiler_flags=arch_compiler_flags,
            compiler_flags=compiler_flags,
            known_warnings=known_warnings,
            headers=headers,
            header_namespace=header_namespace,
            compiler_specific_flags=compiler_specific_flags,
            supports_coverage=supports_coverage,
            tags=tags,
            linker_flags=linker_flags,
            arch_preprocessor_flags=arch_preprocessor_flags,
            preprocessor_flags=preprocessor_flags,
            prefix_header=prefix_header,
            precompiled_header=precompiled_header,
            propagated_pp_flags=propagated_pp_flags,
            link_whole=link_whole,
            global_symbols=global_symbols,
            allocator=allocator,
            args=args,
            external_deps=external_deps,
            type=type,
            owner=owner,
            emails=emails,
            dlopen_enabled=dlopen_enabled,
            nodefaultlibs=nodefaultlibs,
            shared_system_deps=shared_system_deps,
            system_include_paths=system_include_paths,
            split_symbols=split_symbols,
            env=env,
            use_default_test_main=use_default_test_main,
            lib_name=lib_name,
            nvcc_flags=nvcc_flags,
            hip_flags=hip_flags,
            enable_lto=enable_lto,
            hs_profile=hs_profile,
            dont_link_prerequisites=dont_link_prerequisites,
            lex_args=lex_args,
            yacc_args=yacc_args,
            runtime_files=runtime_files,
            additional_coverage_targets=additional_coverage_targets,
            py3_sensitive_deps=py3_sensitive_deps,
            dlls=dlls,
            versions=versions,
            visibility=visibility,
            auto_headers=auto_headers,
            preferred_linkage=preferred_linkage,
            os_deps=os_deps,
            os_linker_flags=os_linker_flags,
            autodeps_keep=autodeps_keep,
            undefined_symbols=undefined_symbols,
            modular_headers=modular_headers,
            modules=modules,
            overridden_link_style=overridden_link_style,
            rule_specific_deps=rule_specific_deps,
            rule_specific_preprocessor_flags=rule_specific_preprocessor_flags,
            tests=tests,
        )
        return [Rule(buck_rule_type, attributes)]

    def get_allowed_args(self):
        """
        Return the allowed arguments for this rule.
        """

        # Arguments that apply to all C/C++ rules.
        args = {
            'arch_compiler_flags',
            'arch_preprocessor_flags',
            'auto_headers',
            'compiler_flags',
            'compiler_specific_flags',
            'deps',
            'external_deps',
            'global_symbols',
            'header_namespace',
            'headers',
            'known_warnings',
            'lex_args',
            'linker_flags',
            'modules',
            'name',
            'nodefaultlibs',
            'nvcc_flags',
            'hip_flags',
            'precompiled_header',
            'preprocessor_flags',
            'py3_sensitive_deps',
            'shared_system_deps',
            'srcs',
            'supports_coverage',
            'system_include_paths',
            'visibility',
            'yacc_args',
            'additional_coverage_targets',
            'autodeps_keep',
            'tags',
        }

        # Set rule-type-specific args.
        rtype = self.get_fbconfig_rule_type()

        if rtype in ('cpp_benchmark', 'cpp_unittest'):
            args.update([
                'args',
                'emails',
                'env',
                'owner',
                'runtime_files',
                'tags',
            ])

        if rtype == 'cpp_unittest':
            args.update([
                'type',
                'use_default_test_main',
            ])

        if rtype == 'cpp_binary':
            args.update([
                'dlopen_enabled',
                'dont_link_prerequisites',
                'enable_lto',
                'hs_profile',
                'split_symbols',
                'os_deps',
                'os_linker_flags',
            ])

        if rtype in ('cpp_benchmark', 'cpp_binary', 'cpp_unittest'):
            args.update([
                'allocator',
                'dlls',
                'versions',
            ])

        if rtype == 'cpp_library':
            args.update([
                'lib_name',
                'link_whole',
                'modular_headers',
                'os_deps',
                'os_linker_flags',
                'preferred_linkage',
                'propagated_pp_flags',
                'undefined_symbols',
            ])

        if rtype == 'cpp_precompiled_header':
            args.update([
                'src',
            ])

        if rtype == 'cpp_python_extension':
            args.update([
                'base_module',
                # Intentionally not visible to users!
                #'module_name',
            ])

        if rtype == 'cpp_lua_extension':
            args.update([
                'base_module',
            ])

        if rtype == 'cpp_java_extension':
            args.update([
                'lib_name',
            ])

        if rtype == 'cpp_lua_main_module':
            args.update([
                'embed_deps',
            ])

        return args

    def convert(self, base_path, name, visibility=None, **kwargs):
        """
        Entry point for converting C/C++ rules.
        """
        return self.convert_rule(base_path, name, visibility=visibility, **kwargs)
