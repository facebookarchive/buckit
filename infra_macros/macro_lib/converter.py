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

import os


ALWAYS_ALLOWED_ARGS = {'visibility'}


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def absolute_import(path):
    global _import_macro_lib__imported
    include_defs(path, '_import_macro_lib__imported')  # noqa: F821
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


def import_macro_lib(path):
    return absolute_import('{}/{}.py'.format(
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ))


load("@fbcode_macros//build_defs:export_files.bzl",  # noqa F821
        "export_file", "export_files", "buck_export_file")
load(  # noqa F821
    "@fbcode_macros//build_defs:native_rules.bzl",
    "buck_command_alias",
    "buck_cxx_binary",
    "cxx_genrule",
    "buck_cxx_library",
    "buck_cxx_test",
    "buck_filegroup",
    "buck_genrule",
    "buck_python_binary",
    "buck_python_library",
    "buck_sh_binary",
    "buck_sh_test",
    "buck_zip_file",
    "remote_file",
    "test_suite",
    "versioned_alias",
)
load("@fbcode_macros//build_defs:antlr3_srcs.bzl", "antlr3_srcs")
load("@fbcode_macros//build_defs:dewey_artifact.bzl", "dewey_artifact")
load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
load("@fbcode_macros//build_defs:cpp_library_external.bzl", "cpp_library_external")
load("@fbcode_macros//build_defs:d_library_external.bzl", "d_library_external")
load("@fbcode_macros//build_defs:go_external_library.bzl", "go_external_library")
load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
load("@fbcode_macros//build_defs:java_binary.bzl", "java_binary")
load("@fbcode_macros//build_defs:java_library.bzl", "java_library")
load("@fbcode_macros//build_defs:java_test.bzl", "java_test")
load("@fbcode_macros//build_defs:js_executable.bzl", "js_executable")
load("@fbcode_macros//build_defs:js_node_module_external.bzl", "js_node_module_external")
load("@fbcode_macros//build_defs:js_npm_module.bzl", "js_npm_module")
load("@fbcode_macros//build_defs:java_protoc_library.bzl", "java_protoc_library")
load("@fbcode_macros//build_defs:java_shaded_jar.bzl", "java_shaded_jar")
load("@fbcode_macros//build_defs:ocaml_external_library.bzl", "ocaml_external_library")
load("@fbcode_macros//build_defs:prebuilt_jar.bzl", "prebuilt_jar")
load("@fbcode_macros//build_defs:rust_external_library.bzl", "rust_external_library")
load("@fbcode_macros//build_defs:scala_library.bzl", "scala_library")
load("@fbcode_macros//build_defs:scala_test.bzl", "scala_test")

with allow_unsafe_import():  # noqa: F821
    import sys


base = import_macro_lib('convert/base')
cpp = import_macro_lib('convert/cpp')
cpp_jvm_library = import_macro_lib('convert/cpp_jvm_library')
cpp_library_external_custom = import_macro_lib(
    'convert/cpp_library_external_custom'
)
cpp_module_external = import_macro_lib('convert/cpp_module_external')
custom_unittest = import_macro_lib('convert/custom_unittest')
cython = import_macro_lib('convert/cython')
d = import_macro_lib('convert/d')
discard = import_macro_lib('convert/discard')
go = import_macro_lib('convert/go')
go_bindgen_library = import_macro_lib('convert/go_bindgen_library')
haskell = import_macro_lib('convert/haskell')
image_feature = absolute_import('//fs_image/buck_macros/image_feature.py')
image_layer = absolute_import('//fs_image/buck_macros/image_layer.py')
image_package = absolute_import('//fs_image/buck_macros/image_package.py')
lua = import_macro_lib('convert/lua')
ocaml = import_macro_lib('convert/ocaml')
python = import_macro_lib('convert/python')
rust = import_macro_lib('convert/rust')
rust_bindgen_library = import_macro_lib('convert/rust_bindgen_library')
sphinx = import_macro_lib('convert/sphinx')
swig_library = import_macro_lib('convert/swig_library')
thrift_library = import_macro_lib('convert/thrift_library')
wheel = import_macro_lib('convert/wheel')
try:
    facebook = import_macro_lib('convert/facebook/__init__')
    get_fbonly_converters = facebook.get_fbonly_converters
except ImportError:
    def get_fbonly_converters(context):
        return []


FBCODE_UI_MESSAGE = (
    'Unsupported access to Buck rules! '
    'Please use supported fbcode rules (https://fburl.com/fbcode-targets) '
    'instead.')


class ConversionError(Exception):
    pass


def handle_errors(errors, skip_errors=False):
    """
    Helper function to either print or throw errors resulting from conversion.
    """

    if skip_errors:
        for name, error in errors.items():
            print(name + ': ' + error, file=sys.stderr)
    else:
        msg = ['Conversion failures:']
        for name, error in errors.items():
            msg.append('  ' + name + ': ' + error)
        raise Exception(os.linesep.join(msg))


def convert(context, base_path, rule):
    """
    Convert the python representation of a targets file into a python
    representation of a buck file.
    """

    converters = [
        discard.DiscardingConverter(context, 'cpp_binary_external'),
        discard.DiscardingConverter(context, 'haskell_genscript'),
        cpp_library_external_custom.CppLibraryExternalCustomConverter(context),
        cpp.CppConverter(context, 'cpp_library'),
        cpp.CppConverter(context, 'cpp_binary'),
        cpp.CppConverter(context, 'cpp_unittest'),
        cpp.CppConverter(context, 'cpp_benchmark'),
        cpp.CppConverter(context, 'cpp_precompiled_header'),
        cpp.CppConverter(context, 'cpp_python_extension'),
        cpp.CppConverter(context, 'cpp_java_extension'),
        cpp.CppConverter(context, 'cpp_lua_extension'),
        cpp.CppConverter(context, 'cpp_lua_main_module'),
        cpp.CppConverter(context, 'cpp_node_extension'),
        cpp_jvm_library.CppJvmLibrary(context),
        cpp_module_external.CppModuleExternalConverter(context),
        cython.Converter(context),
        d.DConverter(context, 'd_binary'),
        d.DConverter(context, 'd_library'),
        d.DConverter(context, 'd_unittest', 'd_test'),
        go.GoConverter(context, 'go_binary'),
        go.GoConverter(context, 'go_library'),
        go.GoConverter(context, 'cgo_library'),
        go.GoConverter(context, 'go_unittest', 'go_test'),
        go_bindgen_library.GoBindgenLibraryConverter(context),
        haskell.HaskellConverter(context, 'haskell_binary'),
        haskell.HaskellConverter(context, 'haskell_library'),
        haskell.HaskellConverter(context, 'haskell_unittest', 'haskell_binary'),
        haskell.HaskellConverter(context, 'haskell_ghci'),
        haskell.HaskellConverter(context, 'haskell_haddock'),
        image_feature.ImageFeatureConverter(context),
        image_layer.ImageLayerConverter(context),
        image_package.ImagePackageConverter(context),
        lua.LuaConverter(context, 'lua_library'),
        lua.LuaConverter(context, 'lua_binary'),
        lua.LuaConverter(context, 'lua_unittest'),
        python.PythonConverter(context, 'python_library'),
        python.PythonConverter(context, 'python_binary'),
        python.PythonConverter(context, 'python_unittest'),
        custom_unittest.CustomUnittestConverter(context),
        thrift_library.ThriftLibraryConverter(context),
        swig_library.SwigLibraryConverter(context),
        ocaml.OCamlConverter(context, 'ocaml_library'),
        ocaml.OCamlConverter(context, 'ocaml_binary'),
        rust.RustConverter(context, 'rust_library'),
        rust.RustConverter(context, 'rust_binary'),
        rust.RustConverter(context, 'rust_unittest'),
        rust_bindgen_library.RustBindgenLibraryConverter(context),
        sphinx.SphinxWikiConverter(context),
        sphinx.SphinxManpageConverter(context),
        wheel.PyWheel(context),
        wheel.PyWheelDefault(context),
    ]

    converters += get_fbonly_converters(context)

    converter_map = {}
    new_converter_map = {
        'antlr3_srcs': antlr3_srcs,
        'buck_cxx_binary': buck_cxx_binary,  # noqa F821
        'cxx_genrule': cxx_genrule,  # noqa F821
        'buck_cxx_library': buck_cxx_library,  # noqa F821
        'buck_cxx_test': buck_cxx_test,  # noqa F821
        'buck_export_file': buck_export_file,  # noqa F821
        'buck_filegroup': buck_filegroup,  # noqa F821
        'buck_genrule': buck_genrule,  # noqa F821
        'buck_python_binary': buck_python_binary,  # noqa F821
        'buck_python_library': buck_python_library,  # noqa F821
        'buck_sh_binary': buck_sh_binary,  # noqa F821
        'buck_sh_test': buck_sh_test,  # noqa F821
        'buck_zip_file': buck_zip_file,  # noqa F821
        'dewey_artifact': dewey_artifact,  # noqa F821
        'export_file': export_file,  # noqa F821
        'export_files': export_files,  # noqa F821
        'versioned_alias': versioned_alias,  # noqa F821
        'remote_file': remote_file,  # noqa F821
        'test_suite': test_suite,  # noqa F821
        'buck_command_alias': buck_command_alias,  # noqa F821
        'custom_rule': custom_rule,  # noqa F821
        'go_external_library': go_external_library,  # noqa F821
        'haskell_external_library': haskell_external_library,  # noqa F821
        'java_binary': java_binary,  # noqa F821
        'java_library': java_library,  # noqa F821
        'java_protoc_library': java_protoc_library,  # noqa F821
        'java_shaded_jar': java_shaded_jar,  # noqa F821
        'java_test': java_test,  # noqa F821
        'js_executable': js_executable,  # noqa F821
        'js_node_module_external': js_node_module_external,  # noqa F821
        'js_npm_module': js_npm_module,  # noqa F821
        'ocaml_external_library': ocaml_external_library,  # noqa F821
        'prebuilt_jar': prebuilt_jar,  # noqa F821
        'rust_external_library': rust_external_library,  # noqa F821
        'scala_library': scala_library,  # noqa F821
        'scala_test': scala_test,  # noqa F821
        'cpp_library_external': cpp_library_external,
        'd_library_external': d_library_external,
    }

    for converter in converters:
        converter_map[converter.get_fbconfig_rule_type()] = converter

    converter = converter_map.get(rule.type, new_converter_map.get(rule.type))

    if converter is None:
        name = '{0}:{1}'.format(base_path, rule.attributes['name'])
        raise ValueError('unknown rule type %s for %s' % (rule.type, name))

    # New style rules don't return anything, they instantiate rules
    # directly. Just return an empty list here so that callers, like
    # macros.py, will not break for now. Eventually most of this code will
    # disappear
    if rule.type in new_converter_map:
        converter(**rule.attributes)
        return []

    # Verify arguments for old style rules. Newer rules should blow up
    # with a more readable message.
    allowed_args = converter_map[rule.type].get_allowed_args()
    if allowed_args is not None:
        for attribute in rule.attributes:
            if (attribute not in allowed_args and
                    attribute not in ALWAYS_ALLOWED_ARGS):
                raise TypeError(
                    '{}() got an unexpected keyword argument: {!r}'
                    .format(rule.type, attribute))

    # Potentially convert from a generator
    return list(converter_map[rule.type].convert(
        base_path,
        **rule.attributes
    ))
