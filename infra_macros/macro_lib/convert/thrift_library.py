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

import itertools
import pipes

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
target = import_macro_lib('fbcode_target')
load("@bazel_skylib//lib:collections.bzl", "collections")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@fbcode_macros//build_defs/lib:python_typing.bzl",
     "get_typing_config_target")
load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
load("@fbcode_macros//build_defs:custom_rule.bzl", "get_project_root_from_gen_dir")
load("@fbcode_macros//build_defs:java_library.bzl", "java_library")
load("@fbcode_macros//build_defs:cython_library.bzl", "cython_library")
load("@fbcode_macros//build_defs/lib:merge_tree.bzl", "merge_tree")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:haskell_common.bzl", "haskell_common")
load("@fbcode_macros//build_defs/lib:haskell_rules.bzl", "haskell_rules")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:python_typing.bzl", "gen_typing_config")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool", "read_list")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load(
    "@fbcode_macros//build_defs:thrift_library.bzl",
    "py_remote_binaries",
    "CONVERTERS",
    "NAMES_TO_LANG",
    "parse_thrift_args",
    "parse_thrift_options",
    "fixup_thrift_srcs",
    "get_exported_include_tree",
    "filter_language_specific_kwargs",
    "get_languages",
    "generate_compile_rule",
    "generate_generated_source_rules",
    "convert_macros",
)
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_string", "is_tuple", "is_list")

class ThriftLibraryConverter(base.Converter):

    def __init__(self):
        super(ThriftLibraryConverter, self).__init__()

    def get_fbconfig_rule_type(self):
        return 'thrift_library'

    def get_buck_rule_type(self):
        return 'thrift_library'

    def get_allowed_args(self):
        """
        Return the list of allowed arguments.
        """

        allowed_args = set([
            'cpp2_compiler_flags',
            'cpp2_compiler_specific_flags',
            'cpp2_deps',
            'cpp2_external_deps',
            'cpp2_headers',
            'cpp2_srcs',
            'd_thrift_namespaces',
            'deps',
            'go_pkg_base_path',
            'go_thrift_namespaces',
            'go_thrift_src_inter_deps',
            'hs_includes',
            'hs_namespace',
            'hs_packages',
            'hs_required_symbols',
            'hs2_deps',
            'java_deps',
            'javadeprecated_maven_coords',
            'javadeprecated_maven_publisher_enabled',
            'javadeprecated_maven_publisher_version_prefix',
            'java_swift_maven_coords',
            'languages',
            'name',
            'plugins',
            'py_asyncio_base_module',
            'py_base_module',
            'py_remote_service_router',
            'py_twisted_base_module',
            'py3_namespace',
            'ruby_gem_name',
            'ruby_gem_require_paths',
            'ruby_gem_version',
            'thrift_args',
            'thrift_srcs',
        ])

        # Add the default args based on the languages we support
        langs = []
        langs.extend(NAMES_TO_LANG.values())
        langs.extend([
            'py',
            'py-asyncio',
            'py-twisted',
            'ruby',
        ])
        for lang in langs:
            allowed_args.add('thrift_' + lang.replace('-', '_') + '_options')
        return allowed_args

    def convert(self,
            base_path,
            name,
            thrift_srcs,
            languages=(),
            plugins=(),
            visibility=None,
            thrift_args=(),
            deps=(),

            # Language specific flags
            cpp2_compiler_flags=None,
            cpp2_compiler_specific_flags=None,
            cpp2_deps=None,
            cpp2_external_deps=None,
            cpp2_headers=None,
            cpp2_srcs=None,
            d_thrift_namespaces=None,
            go_pkg_base_path=None,
            go_thrift_namespaces=None,
            go_thrift_src_inter_deps=None,
            hs_includes=None,
            hs_namespace=None,
            hs_packages=None,
            hs_required_symbols=None,
            hs2_deps=None,
            java_deps=None,
            javadeprecated_maven_coords=None,
            javadeprecated_maven_publisher_enabled=None,
            javadeprecated_maven_publisher_version_prefix=None,
            java_swift_maven_coords=None,
            py_asyncio_base_module=None,
            py_base_module=None,
            py_remote_service_router=None,
            py_twisted_base_module=None,
            py3_namespace=None,
            ruby_gem_name=None,
            ruby_gem_require_paths=None,
            ruby_gem_version=None,
            thrift_cpp2_options=None,
            thrift_d_options=None,
            thrift_go_options=None,
            thrift_hs2_options=None,
            thrift_hs_options=None,
            thrift_java_swift_options=None,
            thrift_javadeprecated_apache_options=None,
            thrift_javadeprecated_options=None,
            thrift_js_options=None,
            thrift_ocaml2_options=None,
            thrift_py3_options=None,
            thrift_py_asyncio_options=None,
            thrift_py_options=None,
            thrift_py_twisted_options=None,
            thrift_pyi_asyncio_options=None,
            thrift_pyi_options=None,
            thrift_ruby_options=None,
            thrift_rust_options=None,
            thrift_thriftdoc_py_options=None,
        ):
        visibility = get_visibility(visibility, name)

        supported_languages = read_list(
            'thrift', 'supported_languages', delimiter=None, required=False,
        )
        if supported_languages != None:
            languages = sets.to_list(
                sets.intersection(
                    sets.make(languages), sets.make(supported_languages)))

        # Parse incoming options.
        thrift_srcs = fixup_thrift_srcs(thrift_srcs or {})
        thrift_args = parse_thrift_args(thrift_args)
        languages = get_languages(languages)
        deps = [src_and_dep_helpers.convert_build_target(base_path, d) for d in deps]


        # Convert rules we support via macros.
        if languages:
            language_kwargs = filter_language_specific_kwargs(
                cpp2_compiler_flags=cpp2_compiler_flags,
                cpp2_compiler_specific_flags=cpp2_compiler_specific_flags,
                cpp2_deps=cpp2_deps,
                cpp2_external_deps=cpp2_external_deps,
                cpp2_headers=cpp2_headers,
                cpp2_srcs=cpp2_srcs,
                d_thrift_namespaces=d_thrift_namespaces,
                go_pkg_base_path=go_pkg_base_path,
                go_thrift_namespaces=go_thrift_namespaces,
                go_thrift_src_inter_deps=go_thrift_src_inter_deps,
                hs_includes=hs_includes,
                hs_namespace=hs_namespace,
                hs_packages=hs_packages,
                hs_required_symbols=hs_required_symbols,
                hs2_deps=hs2_deps,
                java_deps=java_deps,
                javadeprecated_maven_coords=javadeprecated_maven_coords,
                javadeprecated_maven_publisher_enabled=javadeprecated_maven_publisher_enabled,
                javadeprecated_maven_publisher_version_prefix=javadeprecated_maven_publisher_version_prefix,
                java_swift_maven_coords=java_swift_maven_coords,
                py_asyncio_base_module=py_asyncio_base_module,
                py_base_module=py_base_module,
                py_remote_service_router=py_remote_service_router,
                py_twisted_base_module=py_twisted_base_module,
                py3_namespace=py3_namespace,
                ruby_gem_name=ruby_gem_name,
                ruby_gem_require_paths=ruby_gem_require_paths,
                ruby_gem_version=ruby_gem_version,
                thrift_cpp2_options=thrift_cpp2_options,
                thrift_d_options=thrift_d_options,
                thrift_go_options=thrift_go_options,
                thrift_hs2_options=thrift_hs2_options,
                thrift_hs_options=thrift_hs_options,
                thrift_java_swift_options=thrift_java_swift_options,
                thrift_javadeprecated_apache_options=thrift_javadeprecated_apache_options,
                thrift_javadeprecated_options=thrift_javadeprecated_options,
                thrift_js_options=thrift_js_options,
                thrift_ocaml2_options=thrift_ocaml2_options,
                thrift_py3_options=thrift_py3_options,
                thrift_py_asyncio_options=thrift_py_asyncio_options,
                thrift_py_options=thrift_py_options,
                thrift_py_twisted_options=thrift_py_twisted_options,
                thrift_pyi_asyncio_options=thrift_pyi_asyncio_options,
                thrift_pyi_options=thrift_pyi_options,
                thrift_ruby_options=thrift_ruby_options,
                thrift_rust_options=thrift_rust_options,
                thrift_thriftdoc_py_options=thrift_thriftdoc_py_options,
            )

            convert_macros(
                base_path=base_path,
                name=name,
                thrift_srcs=thrift_srcs,
                languages=languages,
                plugins=plugins,
                visibility=visibility,
                thrift_args=thrift_args,
                deps=deps,
                **language_kwargs
            )

        # If python is listed in languages, then also generate the py-remote
        # rules.
        if 'py' in languages or 'python' in languages:
            py_remote_binaries(
                base_path,
                name=name,
                thrift_srcs=fixup_thrift_srcs(thrift_srcs),
                base_module=py_base_module,
                include_sr=py_remote_service_router,
                visibility=visibility)

        return []
