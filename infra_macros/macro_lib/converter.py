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


load("@fbcode_macros//build_defs:cgo_library.bzl", "cgo_library")
load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
load("@fbcode_macros//build_defs:cpp_library_external.bzl", "cpp_library_external")
load("@fbcode_macros//build_defs:cpp_benchmark.bzl", "cpp_benchmark")
load("@fbcode_macros//build_defs:cpp_lua_extension.bzl", "cpp_lua_extension")
load("@fbcode_macros//build_defs:cpp_lua_main_module.bzl", "cpp_lua_main_module")
load("@fbcode_macros//build_defs:cpp_java_extension.bzl", "cpp_java_extension")
load("@fbcode_macros//build_defs:cpp_module_external.bzl", "cpp_module_external")
load("@fbcode_macros//build_defs:cpp_node_extension.bzl", "cpp_node_extension")
load("@fbcode_macros//build_defs:cpp_python_extension.bzl", "cpp_python_extension")
load("@fbcode_macros//build_defs:cpp_precompiled_header.bzl", "cpp_precompiled_header")
load("@fbcode_macros//build_defs:cpp_unittest.bzl", "cpp_unittest")
load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
load("@fbcode_macros//build_defs:cpp_library_external_custom.bzl", "cpp_library_external_custom")
load("@fbcode_macros//build_defs:cpp_binary.bzl", "cpp_binary")
load("@fbcode_macros//build_defs:cython_library.bzl", "cython_library")
load("@fbcode_macros//build_defs:d_binary.bzl", "d_binary")
load("@fbcode_macros//build_defs:d_library.bzl", "d_library")
load("@fbcode_macros//build_defs:d_library_external.bzl", "d_library_external")
load("@fbcode_macros//build_defs:d_unittest.bzl", "d_unittest")
load("@fbcode_macros//build_defs:discard.bzl", "discard")
load("@fbcode_macros//build_defs:go_binary.bzl", "go_binary")
load("@fbcode_macros//build_defs:go_bindgen_library.bzl", "go_bindgen_library")
load("@fbcode_macros//build_defs:go_library.bzl", "go_library")
load("@fbcode_macros//build_defs:go_unittest.bzl", "go_unittest")
load("@fbcode_macros//build_defs:haskell_binary.bzl", "haskell_binary")
load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
load("@fbcode_macros//build_defs:haskell_haddock.bzl", "haskell_haddock")
load("@fbcode_macros//build_defs:haskell_ghci.bzl", "haskell_ghci")
load("@fbcode_macros//build_defs:haskell_library.bzl", "haskell_library")
load("@fbcode_macros//build_defs:haskell_unittest.bzl", "haskell_unittest")
load("@fbcode_macros//build_defs:js_executable.bzl", "js_executable")
load("@fbcode_macros//build_defs:js_node_module_external.bzl", "js_node_module_external")
load("@fbcode_macros//build_defs:js_npm_module.bzl", "js_npm_module")
load("@fbcode_macros//build_defs:lua_binary.bzl", "lua_binary")
load("@fbcode_macros//build_defs:lua_library.bzl", "lua_library")
load("@fbcode_macros//build_defs:lua_unittest.bzl", "lua_unittest")
load("@fbcode_macros//build_defs:ocaml_binary.bzl", "ocaml_binary")
load("@fbcode_macros//build_defs:ocaml_external_library.bzl", "ocaml_external_library")
load("@fbcode_macros//build_defs:ocaml_library.bzl", "ocaml_library")
load("@fbcode_macros//build_defs:prebuilt_jar.bzl", "prebuilt_jar")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")
load("@fbcode_macros//build_defs:python_library.bzl", "python_library")
load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")
load("@fbcode_macros//build_defs:python_wheel.bzl", "python_wheel")
load("@fbcode_macros//build_defs:python_wheel_default.bzl", "python_wheel_default")
load("@fbcode_macros//build_defs:sphinx_manpage.bzl", "sphinx_manpage")
load("@fbcode_macros//build_defs:sphinx_wiki.bzl", "sphinx_wiki")
load("@fbcode_macros//build_defs:rust_binary.bzl", "rust_binary")
load("@fbcode_macros//build_defs:rust_bindgen_library.bzl", "rust_bindgen_library")
load("@fbcode_macros//build_defs:rust_external_library.bzl", "rust_external_library")
load("@fbcode_macros//build_defs:rust_library.bzl", "rust_library")
load("@fbcode_macros//build_defs:rust_unittest.bzl", "rust_unittest")
load("@fbcode_macros//build_defs:scala_test.bzl", "scala_test")
load("@fbcode_macros//build_defs:swig_library.bzl", "swig_library")


_CONVERTER_MAP = {
    'cgo_library': cgo_library,  # noqa F821
    'cpp_benchmark': cpp_benchmark,  # noqa F821
    'cpp_binary_external': discard,  # noqa F821
    'cpp_binary': cpp_binary,  # noqa F821
    'cpp_java_extension': cpp_java_extension,  # noqa F821
    'cpp_library_external_custom': cpp_library_external_custom,  # noqa F821
    'cpp_library_external': cpp_library_external,  # noqa F821
    'cpp_library': cpp_library,  # noqa F821
    'cpp_lua_extension': cpp_lua_extension,  # noqa F821
    'cpp_lua_main_module': cpp_lua_main_module,  # noqa F821
    'cpp_module_external': cpp_module_external,  # noqa F821
    'cpp_node_extension': cpp_node_extension,  # noqa F821
    'cpp_precompiled_header': cpp_precompiled_header,  # noqa F821
    'cpp_python_extension': cpp_python_extension,  # noqa F821
    'cpp_unittest': cpp_unittest,  # noqa F821
    'custom_rule': custom_rule,  # noqa F821
    'cython_library': cython_library,  # noqa F821
    'd_binary': d_binary,  # noqa F821
    'd_library_external': d_library_external,  # noqa F821
    'd_library': d_library,  # noqa F821
    'd_unittest': d_unittest,  # noqa F821
    'go_binary': go_binary,  # noqa F821
    'go_bindgen_library': go_bindgen_library,  # noqa F821
    'go_library': go_library,  # noqa F821
    'go_unittest': go_unittest,  # noqa F821
    'haskell_binary': haskell_binary,  # noqa F821
    'haskell_external_library': haskell_external_library,  # noqa F821
    'haskell_ghci': haskell_ghci,  # noqa F821
    'haskell_haddock': haskell_haddock,  # noqa F821
    'haskell_library': haskell_library,  # noqa F821
    'haskell_unittest': haskell_unittest,  # noqa F821
    'js_executable': js_executable,  # noqa F821
    'js_node_module_external': js_node_module_external,  # noqa F821
    'js_npm_module': js_npm_module,  # noqa F821
    'lua_binary': lua_binary,  # noqa F821
    'lua_library': lua_library,  # noqa F821
    'lua_unittest': lua_unittest,  # noqa F821
    'ocaml_binary': ocaml_binary,  # noqa F821
    'ocaml_external_library': ocaml_external_library,  # noqa F821
    'ocaml_library': ocaml_library,  # noqa F821
    'prebuilt_jar': prebuilt_jar,  # noqa F821
    'python_binary': python_binary,  # noqa F821
    'python_library': python_library,  # noqa F821
    'python_unittest': python_unittest,  # noqa F821
    'python_wheel_default': python_wheel_default,  # noqa F821
    'python_wheel': python_wheel,  # noqa F821
    'rust_binary': rust_binary,  # noqa F821
    'rust_bindgen_library': rust_bindgen_library,  # noqa F821
    'rust_external_library': rust_external_library,  # noqa F821
    'rust_library': rust_library,  # noqa F821
    'rust_unittest': rust_unittest,  # noqa F821
    'scala_test': scala_test,  # noqa F821
    'sphinx_manpage': sphinx_manpage,  # noqa F821
    'sphinx_wiki': sphinx_wiki,  # noqa F821
    'swig_library': swig_library,  # noqa F821
}


def convert(rule_type, attributes):
    """
    Convert the python representation of a targets file into a python
    representation of a buck file.
    """

    converter = _CONVERTER_MAP.get(rule_type)

    if converter is None:
        name = '{0}:{1}'.format(native.package_name(), attributes['name'])
        raise ValueError('unknown rule type %s for %s' % (rule_type, name))

    converter(**attributes)
