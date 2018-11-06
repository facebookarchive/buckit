# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import platform

import tests.utils


class ConfigTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:config.bzl", "config")]

    @tests.utils.with_project()
    def test_simple_properties_defaults(self, root):
        current_os = None
        if platform.system().lower() == "darwin":
            current_os = "mac"
        elif platform.system().lower() == "linux":
            current_os = "linux"
        elif platform.system().lower() == "windows":
            current_os = "windows"

        expected = [
            False,  # get_add_auto_headers_glob
            {
                "jemalloc": ["jemalloc//jemalloc:jemalloc"],
                "jemalloc_debug": ["jemalloc//jemalloc:jemalloc_debug"],
                "tcmalloc": ["tcmalloc//tcmalloc:tcmalloc"],
                "malloc": [],
            },  # get_allocators
            False,  # get_auto_fdo_enabled
            "dev",  # get_build_mode
            "gcc",  # get_default_compiler_family
            None,  # get_global_compiler_family
            current_os,  # get_coverage
            "fbcode",  # get_current_repo_name
            None,  # get_cython_compiler
            "malloc",  # get_default_allocator
            "static",  # get_default_link_style
            False,  # get_fbcode_style_deps
            True,  # get_fbcode_style_deps_are_third_party
            None,  # get_gtest_lib_dependencies
            None,  # get_gtest_main_dependency
            [],  # get_header_namespace_whitelist
            None,  # get_lto_type
            False,  # get_require_platform
            "",  # get_third_party_buck_directory
            "",  # get_third_party_config_path
            False,  # get_third_party_use_build_subdir
            False,  # get_third_party_use_platform_subdir
            False,  # get_third_party_use_tools_subdir
            "thrift//thrift/compiler/py:thrift",  # get_thrift2_compiler
            "thrift//thrift/compiler:thrift",  # get_thrift_compiler
            "",  # get_thrift_hs2_compiler
            "",  # get_thrift_ocaml_compiler
            "",  # get_thrift_swift_compiler
            "thrift//thrift/compiler/generate/templates:templates",  # get_thrift_templates
            False,  # get_unknown_cells_are_third_party
            False,  # get_use_build_info_linker_flags
            False,  # get_use_custom_par_args
        ]

        statements = [
            "config.get_add_auto_headers_glob()",
            "config.get_allocators()",
            "config.get_auto_fdo_enabled()",
            "config.get_build_mode()",
            "config.get_default_compiler_family()",
            "config.get_global_compiler_family()",
            "config.get_current_os()",
            "config.get_current_repo_name()",
            "config.get_cython_compiler()",
            "config.get_default_allocator()",
            "config.get_default_link_style()",
            "config.get_fbcode_style_deps()",
            "config.get_fbcode_style_deps_are_third_party()",
            "config.get_gtest_lib_dependencies()",
            "config.get_gtest_main_dependency()",
            "config.get_header_namespace_whitelist()",
            "config.get_lto_type()",
            "config.get_require_platform()",
            "config.get_third_party_buck_directory()",
            "config.get_third_party_config_path()",
            "config.get_third_party_use_build_subdir()",
            "config.get_third_party_use_platform_subdir()",
            "config.get_third_party_use_tools_subdir()",
            "config.get_thrift2_compiler()",
            "config.get_thrift_compiler()",
            "config.get_thrift_hs2_compiler()",
            "config.get_thrift_ocaml_compiler()",
            "config.get_thrift_swift_compiler()",
            "config.get_thrift_templates()",
            "config.get_unknown_cells_are_third_party()",
            "config.get_use_build_info_linker_flags()",
            "config.get_use_custom_par_args()",
        ]

        ret = root.runUnitTests(self.includes, statements)

        self.assertSuccess(ret)
        self.assertEqual(expected, ret.debug_lines)

    @tests.utils.with_project()
    def test_simple_properties(self, root):
        current_os = None
        if platform.system().lower() == "darwin":
            current_os = "mac"
        elif platform.system().lower() == "linux":
            current_os = "linux"
        elif platform.system().lower() == "windows":
            current_os = "windows"

        buckconfig = {
            "cxx": {"profile": "//tools:profile"},
            "fbcode": {
                "add_auto_headers_glob": "true",
                "allocators.jemalloc": "//foo:jemalloc,//foo:jemalloc_other",
                "allocators.jemalloc_debug": "//foo:jemalloc_debug",
                "allocators.tcmalloc": "//foo:tcmalloc",
                "allocators.malloc": "//foo:malloc",
                "build_mode": "opt",
                "global_compiler": "clang",
                "current_repo_name": "third-party",
                "default_allocator": "jemalloc",
                "fbcode_style_deps": "true",
                "fbcode_style_deps_are_third_party": "false",
                "gtest_lib_dependencies": "//third-party/gtest:gtest",
                "gtest_main_dependency": "//third-party/gtest:gtest_main",
                "header_namespace_whitelist": "//package:rule, //package2:rule3",
                "lto_type": "thin",
                "require_platform": "true",
                "sanitizer": "asan",
                "third_party_buck_directory": "third-party-buck",
                "third_party_config_path": "third-party-buck/config.py",
                "third_party_use_build_subdir": "true",
                "third_party_use_platform_subdir": "true",
                "third_party_use_tools_subdir": "true",
                "unknown_cells_are_third_party": "true",
                "use_build_info_linker_flags": "true",
                "use_custom_par_args": "true",
            },
            "cython": {"cython_compiler": "//tools:cython"},
            "defaults.cxx_library": {"type": "shared"},
            "thrift": {
                "compiler": "//thrift/compiler:thrift",
                "compiler2": "//thrift/compiler/py:thrift",
                "hs2_compiler": "//thrift/compiler:hs2",
                "ocaml_compiler": "//thrift/compiler:ocaml",
                "swift_compiler": "//thrift/compiler:swift",
                "templates": "//thrift/compiler/generate/templates:templates",
            },
        }

        expected = [
            True,  # get_add_auto_headers_glob
            {
                "jemalloc": ["//foo:jemalloc", "//foo:jemalloc_other"],
                "jemalloc_debug": ["//foo:jemalloc_debug"],
                "tcmalloc": ["//foo:tcmalloc"],
                "malloc": ["//foo:malloc"],
            },  # get_allocators
            True,  # get_auto_fdo_enabled
            "opt",  # get_build_mode
            "clang",  # get_global_compiler_family
            current_os,  # get_coverage
            "third-party",  # get_current_repo_name
            "//tools:cython",  # get_cython_compiler
            "jemalloc",  # get_default_allocator
            "shared",  # get_default_link_style
            True,  # get_fbcode_style_deps
            False,  # get_fbcode_style_deps_are_third_party
            "//third-party/gtest:gtest",  # get_gtest_lib_dependencies
            "//third-party/gtest:gtest_main",  # get_gtest_main_dependency
            [
                ("//package", "rule"),
                ("//package2", "rule3"),
            ],  # get_header_namespace_whitelist
            "thin",  # get_lto_type
            True,  # get_require_platform
            "third-party-buck",  # get_third_party_buck_directory
            "third-party-buck/config.py",  # get_third_party_config_path
            True,  # get_third_party_use_build_subdir
            True,  # get_third_party_use_platform_subdir
            True,  # get_third_party_use_tools_subdir
            "//thrift/compiler/py:thrift",  # get_thrift2_compiler
            "//thrift/compiler:thrift",  # get_thrift_compiler
            "//thrift/compiler:hs2",  # get_thrift_hs2_compiler
            "//thrift/compiler:ocaml",  # get_thrift_ocaml_compiler
            "//thrift/compiler:swift",  # get_thrift_swift_compiler
            "//thrift/compiler/generate/templates:templates",  # get_thrift_templates
            True,  # get_unknown_cells_are_third_party
            True,  # get_use_build_info_linker_flags
            True,  # get_use_custom_par_args
        ]

        statements = [
            "config.get_add_auto_headers_glob()",
            "config.get_allocators()",
            "config.get_auto_fdo_enabled()",
            "config.get_build_mode()",
            "config.get_global_compiler_family()",
            "config.get_current_os()",
            "config.get_current_repo_name()",
            "config.get_cython_compiler()",
            "config.get_default_allocator()",
            "config.get_default_link_style()",
            "config.get_fbcode_style_deps()",
            "config.get_fbcode_style_deps_are_third_party()",
            "config.get_gtest_lib_dependencies()",
            "config.get_gtest_main_dependency()",
            "config.get_header_namespace_whitelist()",
            "config.get_lto_type()",
            "config.get_require_platform()",
            "config.get_third_party_buck_directory()",
            "config.get_third_party_config_path()",
            "config.get_third_party_use_build_subdir()",
            "config.get_third_party_use_platform_subdir()",
            "config.get_third_party_use_tools_subdir()",
            "config.get_thrift2_compiler()",
            "config.get_thrift_compiler()",
            "config.get_thrift_hs2_compiler()",
            "config.get_thrift_ocaml_compiler()",
            "config.get_thrift_swift_compiler()",
            "config.get_thrift_templates()",
            "config.get_unknown_cells_are_third_party()",
            "config.get_use_build_info_linker_flags()",
            "config.get_use_custom_par_args()",
        ]

        root.updateBuckconfigWithDict(buckconfig)
        ret = root.runUnitTests(self.includes, statements)

        self.assertSuccess(ret)
        self.assertEqual(expected, ret.debug_lines)

    @tests.utils.with_project()
    def test_compiler_family_uses_cxx_cxx_if_fbcode_compiler_family_missing(self, root):
        root.updateBuckconfig("cxx", "cxx", "test-clang")
        ret = root.runUnitTests(self.includes, ["config.get_default_compiler_family()"])

        self.assertSuccess(ret)
        self.assertEqual("clang", ret.debug_lines[0])
