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
            rule_specific_preprocessor_flags=None):
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


# TODO: These are temporary until all logic is extracted into cpp_common
class CppLibraryConverter(CppConverter):
    def __init__(self, context):
        super(CppLibraryConverter, self).__init__(context, 'cpp_library')

    def convert(self, *args, **kwargs):
        return super(CppLibraryConverter, self).convert(
            cpp_rule_type = 'cpp_library',
            buck_rule_type = 'cxx_library',
            is_library = True,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )

class CppBinaryConverter(CppConverter):
    def __init__(self, context):
        super(CppBinaryConverter, self).__init__(context, 'cpp_binary')

    def convert(self, *args, **kwargs):
        return super(CppBinaryConverter, self).convert(
            cpp_rule_type = 'cpp_binary',
            buck_rule_type = 'cxx_binary',
            is_library = False,
            is_buck_binary = True,
            is_test = False,
            is_deployable = True,
            *args,
            **kwargs
        )

class CppUnittestConverter(CppConverter):
    def __init__(self, context):
        super(CppUnittestConverter, self).__init__(context, 'cpp_unittest')

    def convert(self, *args, **kwargs):
        return super(CppUnittestConverter, self).convert(
            cpp_rule_type = 'cpp_unittest',
            buck_rule_type = 'cxx_test',
            is_library = False,
            is_buck_binary = True,
            is_test = True,
            is_deployable = True,
            *args,
            **kwargs
        )

class CppBenchmarkConverter(CppConverter):
    def __init__(self, context):
        super(CppBenchmarkConverter, self).__init__(context, 'cpp_benchmark')

    def convert(self, *args, **kwargs):
        return super(CppBenchmarkConverter, self).convert(
            cpp_rule_type = 'cpp_benchmark',
            buck_rule_type = 'cxx_binary',
            is_library = False,
            is_buck_binary = True,
            is_test = False,
            is_deployable = True,
            *args,
            **kwargs
        )

class CppNodeExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppNodeExtensionConverter, self).__init__(context, 'cpp_node_extension')

    def convert(
            self,
            base_path,
            name,
            dlopen_enabled=None,
            visibility=None,
            **kwargs):

        # Delegate to the main conversion function, making sure that we build
        # the extension into a statically linked monolithic DSO.
        rules = self.convert_rule(
            base_path,
            name + '-extension',
            cpp_rule_type = 'cpp_node_extension',
            buck_rule_type = 'cxx_binary',
            is_library = False,
            is_buck_binary = True,
            is_test = False,
            is_deployable = False,
            dlopen_enabled=True,
            visibility=visibility,
            overridden_link_style = 'static_pic',
            rule_specific_deps = [
                target_utils.ThirdPartyRuleTarget('node', 'node-headers')
            ],
            **kwargs)

        # This is a bit weird, but `prebuilt_cxx_library` rules can only
        # accepted generated libraries that reside in a directory.  So use
        # a genrule to copy the library into a lib dir using it's soname.
        dest = paths.join('node_modules', name, name + '.node')
        native.genrule(
            name = name,
            visibility = visibility,
            out = name + "-modules",
            cmd = ' && '.join([
                'mkdir -p $OUT/{}'.format(paths.dirname(dest)),
                'cp $(location :{}-extension) $OUT/{}'.format(name, dest),
            ]),
        )

        return rules

class CppPrecompiledHeaderConverter(CppConverter):
    def __init__(self, context):
        super(CppPrecompiledHeaderConverter, self).__init__(context, 'cpp_precompiled_header')

    def convert(self, *args, **kwargs):
        return super(CppPrecompiledHeaderConverter, self).convert(
            cpp_rule_type = 'cpp_precompiled_header',
            buck_rule_type = 'cxx_precompiled_header',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )

class CppPythonExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppPythonExtensionConverter, self).__init__(context, 'cpp_python_extension')

    def convert(self, base_path, name, visibility=None, *args, **kwargs):
        ret = super(CppPythonExtensionConverter, self).convert(
            base_path = base_path,
            name = name,
            visibility = visibility,
            cpp_rule_type = 'cpp_python_extension',
            buck_rule_type = 'cxx_python_extension',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            rule_specific_deps = [
                target_utils.ThirdPartyRuleTarget('python', 'python')
            ],
            *args,
            **kwargs
        )
        # Generate an empty typing_config
        ret.append(self.gen_typing_config(name, visibility=visibility))
        return ret

class CppJavaExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppJavaExtensionConverter, self).__init__(context, 'cpp_java_extension')

    def convert(
            self,
            base_path,
            name,
            visibility=None,
            lib_name=None,
            dlopen_enabled=None,
            *args,
            **kwargs):

        rules = []

        # If we're not building in `dev` mode, then build extensions as
        # monolithic statically linked C/C++ shared libs.  We do this by
        # overriding some parameters to generate the extension as a dlopen-
        # enabled C/C++ binary, which also requires us generating the rule
        # under a different name, so we can use the user-facing name to
        # wrap the C/C++ binary in a prebuilt C/C++ library.
        if not config.get_build_mode().startswith('dev'):
            real_name = name
            name = name + '-extension'
            soname = (
                'lib{}.so'.format(
                    lib_name or
                    paths.join(base_path, name).replace('/', '_')))
            dlopen_enabled = {'soname': soname}
            lib_name = None

        # Delegate to the main conversion function, using potentially altered
        # parameters from above.
        if config.get_build_mode().startswith("dev"):
            buck_rule_type = 'cxx_library'
            is_buck_binary = False
        else:
            buck_rule_type = 'cxx_binary'
            is_buck_binary = True
        rules.extend(
            super(CppJavaExtensionConverter, self).convert_rule(
                base_path,
                name,
                cpp_rule_type = 'cpp_java_extension',
                buck_rule_type = buck_rule_type,
                is_library = False,
                is_buck_binary = is_buck_binary,
                is_test = False,
                is_deployable = False,
                dlopen_enabled=dlopen_enabled,
                lib_name=lib_name,
                visibility=visibility,
                **kwargs))

        # If we're building the monolithic extension, then setup additional
        # rules to wrap the extension in a prebuilt C/C++ library consumable
        # by Java dependents.
        if not config.get_build_mode().startswith('dev'):

            # Wrap the extension in a `prebuilt_cxx_library` rule
            # using the user-facing name.  This is what Java library
            # dependents will depend on.
            platform = platform_utils.get_buck_platform_for_base_path(base_path)
            native.prebuilt_cxx_library(
                name = real_name,
                visibility = visibility,
                soname = soname,
                shared_lib = ':{}#{}'.format(name, platform),
            )

        return rules

class CppLuaExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppLuaExtensionConverter, self).__init__(context, 'cpp_lua_extension')

    def convert(self, base_path, name, base_module=None, *args, **kwargs):
        return super(CppLuaExtensionConverter, self).convert(
            cpp_rule_type = 'cpp_lua_extension',
            buck_rule_type = 'cxx_lua_extension',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            base_module = lua_common.get_lua_base_module(base_path, base_module),
            base_path = base_path,
            name = name,
            rule_specific_preprocessor_flags = [
                '-DLUAOPEN={}'.format(
                    lua_common.get_lua_init_symbol(base_path, name, base_module))
            ],
            *args,
            **kwargs
        )

class CppLuaMainModuleConverter(CppConverter):
    def __init__(self, context):
        super(CppLuaMainModuleConverter, self).__init__(context, 'cpp_lua_main_module')

    def convert(self, base_path, name, embed_deps=True, *args, **kwargs):
        # Lua main module rules depend on are custom lua main.
        #
        # When `embed_deps` is set, auto-dep deps on to the embed restore
        # libraries, which will automatically restore special env vars used
        # for loading the binary.
        if embed_deps:
            rule_specific_deps = [
                target_utils.RootRuleTarget('tools/make_lar', 'lua_main_decl'),
                target_utils.ThirdPartyRuleTarget('LuaJIT', 'luajit'),
                target_utils.RootRuleTarget('common/embed', 'lua'),
                target_utils.RootRuleTarget('common/embed', 'python'),
            ]
        else:
            rule_specific_deps = [
                target_utils.RootRuleTarget('tools/make_lar', 'lua_main_decl'),
                target_utils.ThirdPartyRuleTarget('LuaJIT', 'luajit'),
            ]

        return super(CppLuaMainModuleConverter, self).convert(
            base_path = base_path,
            name = name,
            cpp_rule_type = 'cpp_lua_main_module',
            buck_rule_type = 'cxx_library',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            rule_specific_preprocessor_flags = [
                '-Dmain=lua_main',
                '-includetools/make_lar/lua_main_decl.h',
            ],
            rule_specific_deps = rule_specific_deps,
            *args,
            **kwargs
        )
