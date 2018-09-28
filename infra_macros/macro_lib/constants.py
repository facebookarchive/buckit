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

BUCK_RULES = [
    'android_aar',
    'android_binary',
    'android_build_config',
    'android_library',
    'android_prebuilt_aar',
    'android_resource',
    'apk_genrule',
    'command_alias',
    'cxx_binary',
    'cxx_genrule',
    'cxx_library',
    'cxx_precompiled_header',
    'cxx_test',
    'export_file',
    'filegroup',
    'gen_aidl',
    'genrule',
    'go_binary',
    'go_library',
    'cgo_library',
    'prebuilt_go_library',
    'go_test',
    'jar_genrule',
    'java_binary',
    'java_library',
    'java_test',
    'keystore',
    'ndk_library',
    'ocaml_binary',
    'ocaml_library',
    'prebuilt_jar',
    'prebuilt_native_library',
    'project_config',
    'python_binary',
    'python_library',
    'python_test',
    'rust_binary',
    'rust_library',
    'rust_test',
    'prebuilt_rust_library',
    'sh_binary',
    'sh_test',
    'thrift_library',
    'test_suite',
]

FBCODE_RULES = [
    'antlr3_srcs',
    'cpp_benchmark',
    'cpp_binary',
    'cpp_binary_external',
    'cpp_java_extension',
    'cpp_library',
    'cpp_library_external',
    'cpp_library_external_custom',
    'cpp_lua_extension',
    'cpp_lua_main_module',
    'cpp_module_external',
    'cpp_node_extension',
    'cpp_precompiled_header',
    'cpp_python_extension',
    'cpp_java_extension',
    'cpp_jvm_library',
    'cpp_unittest',
    'custom_rule',
    'custom_unittest',
    'cxx_genrule',
    'cython_library',
    'd_binary',
    'd_library',
    'd_library_external',
    'd_unittest',
    'dewey_artifact',
    'export_file',
    'gen_thrift',
    'go_binary',
    'go_library',
    'cgo_library',
    'go_bindgen_library',
    'go_external_library',
    'go_unittest',
    'haskell_binary',
    'haskell_external_library',
    'haskell_genscript',
    'haskell_ghci',
    'haskell_haddock',
    'haskell_library',
    'haskell_unittest',
    'image_feature',
    'image_layer',
    'java_binary',
    'java_library',
    'java_test',
    'java_protoc_library',
    'java_shaded_jar',
    'js_executable',
    'js_library',
    'js_node_module_external',
    'js_npm_module',
    'lua_binary',
    'lua_library',
    'lua_unittest',
    'ocaml_binary',
    'ocaml_external_library',
    'ocaml_library',
    'protoc_library',
    'python_binary',
    'python_library',
    'python_unittest',
    'remote_file',
    'rust_binary',
    'rust_library',
    'rust_unittest',
    'rust_bindgen_library',
    'rust_external_library',
    'scala_library',
    'scala_test',
    'sphinx_wiki',
    'sphinx_manpage',
    'swig_library',
    'thrift_library',
    'versioned_alias',
    'prebuilt_jar',
    'python_wheel',
    'python_wheel_default',
]
