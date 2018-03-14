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
import re


ALWAYS_ALLOWED_ARGS = {'visibility'}

# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret

load("@fbcode_macros//build_defs:export_files.bzl",
        "export_file", "export_files", "buck_export_file")
load(
    "@fbcode_macros//build_defs:native_rules.bzl",
    "buck_command_alias",
    "buck_cxx_binary",
    "cxx_genrule",
    "buck_cxx_library",
    "buck_cxx_test",
    "buck_genrule",
    "buck_python_binary",
    "buck_python_library",
    "buck_sh_binary",
    "buck_sh_test",
    "remote_file",
    "versioned_alias",
)

with allow_unsafe_import():  # noqa: F821
    import sys


base = import_macro_lib('convert/base')
cpp = import_macro_lib('convert/cpp')
cpp_library_external = import_macro_lib('convert/cpp_library_external')
cpp_library_external_custom = import_macro_lib(
    'convert/cpp_library_external_custom'
)
custom_rule = import_macro_lib('convert/custom_rule')
custom_unittest = import_macro_lib('convert/custom_unittest')
cython = import_macro_lib('convert/cython')
d = import_macro_lib('convert/d')
dewey_artifact = import_macro_lib('convert/dewey_artifact')
discard = import_macro_lib('convert/discard')
go = import_macro_lib('convert/go')
haskell = import_macro_lib('convert/haskell')
haskell_external_library = import_macro_lib('convert/haskell_external_library')
try:
    java = import_macro_lib('convert/java')
    java_plugins = import_macro_lib('convert/java_plugins')
    cpp_jvm_library = import_macro_lib('convert/cpp_jvm_library')
    use_internal_java_converters = True
except ImportError:
    use_internal_java_converters = False
image_feature = import_macro_lib('convert/container_image/image_feature')
js = import_macro_lib('convert/js')
lua = import_macro_lib('convert/lua')
ocaml = import_macro_lib('convert/ocaml')
ocaml_library_external = import_macro_lib('convert/ocaml_library_external')
python = import_macro_lib('convert/python')
rust = import_macro_lib('convert/rust')
rust_bindgen_library = import_macro_lib('convert/rust_bindgen_library')
rust_library_external = import_macro_lib('convert/rust_library_external')
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
        cpp_library_external.CppLibraryExternalConverter(
            context,
            'cpp_library_external'),
        cpp_library_external_custom.CppLibraryExternalCustomConverter(context),
        cpp_library_external.CppLibraryExternalConverter(
            context,
            'd_library_external'),
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
        cython.Converter(context),
        d.DConverter(context, 'd_binary'),
        d.DConverter(context, 'd_library'),
        d.DConverter(context, 'd_unittest', 'd_test'),
        dewey_artifact.DeweyArtifactConverter(context),
        go.GoConverter(context, 'go_binary'),
        go.GoConverter(context, 'go_library'),
        go.GoConverter(context, 'cgo_library'),
        go.GoConverter(context, 'go_unittest', 'go_test'),
        haskell.HaskellConverter(context, 'haskell_binary'),
        haskell.HaskellConverter(context, 'haskell_library'),
        haskell.HaskellConverter(context, 'haskell_unittest', 'haskell_binary'),
        haskell.HaskellConverter(context, 'haskell_ghci'),
        haskell.HaskellConverter(context, 'haskell_haddock'),
        haskell_external_library.HaskellExternalLibraryConverter(context),
        image_feature.ImageFeatureConverter(context),
        lua.LuaConverter(context, 'lua_library'),
        lua.LuaConverter(context, 'lua_binary'),
        lua.LuaConverter(context, 'lua_unittest'),
        python.PythonConverter(context, 'python_library'),
        python.PythonConverter(context, 'python_binary'),
        python.PythonConverter(context, 'python_unittest'),
        js.JsConverter(context, 'js_executable'),
        js.JsConverter(context, 'js_node_module_external'),
        js.JsConverter(context, 'js_npm_module'),
        custom_rule.CustomRuleConverter(context),
        custom_unittest.CustomUnittestConverter(context),
        thrift_library.ThriftLibraryConverter(context),
        swig_library.SwigLibraryConverter(context),
        ocaml_library_external.OCamlLibraryExternalConverter(context),
        ocaml.OCamlConverter(context, 'ocaml_library'),
        ocaml.OCamlConverter(context, 'ocaml_binary'),
        rust.RustConverter(context, 'rust_library'),
        rust.RustConverter(context, 'rust_binary'),
        rust.RustConverter(context, 'rust_unittest'),
        rust_bindgen_library.RustBindgenLibraryConverter(context),
        rust_library_external.RustLibraryExternalConverter(context),
        wheel.PyWheel(context),
        wheel.PyWheelDefault(context),
    ]
    if use_internal_java_converters:
        converters += [
            java.JavaLibraryConverter(context),
            java.JavaBinaryConverter(context),
            java_plugins.JarShadeConverter(context),
            java_plugins.Antlr3Converter(context),
            java_plugins.ProtocConverter(context),
            java_plugins.ScalaLibraryConverter(context),
            java.JavaTestConverter(context),
            java.PrebuiltJarConverter(context),
        ]

    converters += get_fbonly_converters(context)

    converter_map = {}
    new_converter_map = {
        'buck_cxx_binary': buck_cxx_binary,
        'cxx_genrule': cxx_genrule,
        'buck_cxx_library': buck_cxx_library,
        'buck_cxx_test': buck_cxx_test,
        'buck_export_file': buck_export_file,
        'buck_genrule': buck_genrule,
        'buck_python_binary': buck_python_binary,
        'buck_python_library': buck_python_library,
        'buck_sh_binary': buck_sh_binary,
        'buck_sh_test': buck_sh_test,
        'export_file': export_file,
        'export_files': export_files,
        'versioned_alias': versioned_alias,
        'remote_file': remote_file,
        'buck_command_alias': buck_command_alias,
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
