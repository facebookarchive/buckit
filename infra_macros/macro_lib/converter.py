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
load("@fbcode_macros//build_defs:antlr4_srcs.bzl", "antlr4_srcs")
load("@fbcode_macros//build_defs:dewey_artifact.bzl", "dewey_artifact")
load("@fbcode_macros//build_defs:cgo_library.bzl", "cgo_library")
load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
load("@fbcode_macros//build_defs:cpp_library_external.bzl", "cpp_library_external")
load("@fbcode_macros//build_defs:cpp_benchmark.bzl", "cpp_benchmark")
load("@fbcode_macros//build_defs:cpp_lua_extension.bzl", "cpp_lua_extension")
load("@fbcode_macros//build_defs:cpp_lua_main_module.bzl", "cpp_lua_main_module")
load("@fbcode_macros//build_defs:cpp_java_extension.bzl", "cpp_java_extension")
load("@fbcode_macros//build_defs:cpp_jvm_library.bzl", "cpp_jvm_library")
load("@fbcode_macros//build_defs:cpp_module_external.bzl", "cpp_module_external")
load("@fbcode_macros//build_defs:cpp_node_extension.bzl", "cpp_node_extension")
load("@fbcode_macros//build_defs:cpp_python_extension.bzl", "cpp_python_extension")
load("@fbcode_macros//build_defs:cpp_precompiled_header.bzl", "cpp_precompiled_header")
load("@fbcode_macros//build_defs:cpp_unittest.bzl", "cpp_unittest")
load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
load("@fbcode_macros//build_defs:cpp_library_external_custom.bzl", "cpp_library_external_custom")
load("@fbcode_macros//build_defs:cpp_binary.bzl", "cpp_binary")
load("@fbcode_macros//build_defs:custom_unittest.bzl", "custom_unittest")
load("@fbcode_macros//build_defs:d_binary.bzl", "d_binary")
load("@fbcode_macros//build_defs:d_library.bzl", "d_library")
load("@fbcode_macros//build_defs:d_library_external.bzl", "d_library_external")
load("@fbcode_macros//build_defs:d_unittest.bzl", "d_unittest")
load("@fbcode_macros//build_defs:discard.bzl", "discard")
load("@fbcode_macros//build_defs:go_binary.bzl", "go_binary")
load("@fbcode_macros//build_defs:go_bindgen_library.bzl", "go_bindgen_library")
load("@fbcode_macros//build_defs:go_external_library.bzl", "go_external_library")
load("@fbcode_macros//build_defs:go_library.bzl", "go_library")
load("@fbcode_macros//build_defs:go_unittest.bzl", "go_unittest")
load("@fbcode_macros//build_defs:haskell_binary.bzl", "haskell_binary")
load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
load("@fbcode_macros//build_defs:haskell_haddock.bzl", "haskell_haddock")
load("@fbcode_macros//build_defs:haskell_ghci.bzl", "haskell_ghci")
load("@fbcode_macros//build_defs:haskell_library.bzl", "haskell_library")
load("@fbcode_macros//build_defs:haskell_unittest.bzl", "haskell_unittest")
load("@fbcode_macros//build_defs:java_binary.bzl", "java_binary")
load("@fbcode_macros//build_defs:java_library.bzl", "java_library")
load("@fbcode_macros//build_defs:java_test.bzl", "java_test")
load("@fbcode_macros//build_defs:js_executable.bzl", "js_executable")
load("@fbcode_macros//build_defs:js_node_module_external.bzl", "js_node_module_external")
load("@fbcode_macros//build_defs:js_npm_module.bzl", "js_npm_module")
load("@fbcode_macros//build_defs:java_protoc_library.bzl", "java_protoc_library")
load("@fbcode_macros//build_defs:java_shaded_jar.bzl", "java_shaded_jar")
load("@fbcode_macros//build_defs:lua_binary.bzl", "lua_binary")
load("@fbcode_macros//build_defs:lua_library.bzl", "lua_library")
load("@fbcode_macros//build_defs:lua_unittest.bzl", "lua_unittest")
load("@fbcode_macros//build_defs:ocaml_binary.bzl", "ocaml_binary")
load("@fbcode_macros//build_defs:ocaml_external_library.bzl", "ocaml_external_library")
load("@fbcode_macros//build_defs:ocaml_library.bzl", "ocaml_library")
load("@fbcode_macros//build_defs:prebuilt_jar.bzl", "prebuilt_jar")
load("@fbcode_macros//build_defs:python_library.bzl", "python_library")
load("@fbcode_macros//build_defs:python_wheel.bzl", "python_wheel")
load("@fbcode_macros//build_defs:python_wheel_default.bzl", "python_wheel_default")
load("@fbcode_macros//build_defs:rust_binary.bzl", "rust_binary")
load("@fbcode_macros//build_defs:rust_bindgen_library.bzl", "rust_bindgen_library")
load("@fbcode_macros//build_defs:rust_external_library.bzl", "rust_external_library")
load("@fbcode_macros//build_defs:rust_library.bzl", "rust_library")
load("@fbcode_macros//build_defs:rust_unittest.bzl", "rust_unittest")
load("@fbcode_macros//build_defs:scala_library.bzl", "scala_library")
load("@fbcode_macros//build_defs:scala_test.bzl", "scala_test")
load("@fbcode_macros//build_defs:swig_library.bzl", "swig_library")


base = import_macro_lib('convert/base')
cython = import_macro_lib('convert/cython')
try:
    load(  # noqa: F821
        '//fs_image/buck_macros:image_feature.bzl',
        'image_feature',
    )
    load(  # noqa: F821
        '//fs_image/buck_macros:image_layer.bzl',
        'image_layer',
    )
    load(  # noqa: F821
        '//fs_image/buck_macros:image_package.bzl',
        'image_package',
    )
except IOError:
    # Some sparse checkouts don't need `image_*` macros, and fbcode/fs_image
    # is not currently part of the sparse base (while `infra_macros` are).
    image_feature = None
    image_layer = None
    image_package = None
python = import_macro_lib('convert/python')
sphinx = import_macro_lib('convert/sphinx')
thrift_library = import_macro_lib('convert/thrift_library')
try:
    facebook = import_macro_lib('convert/facebook/__init__')
    get_fbonly_converters = facebook.get_fbonly_converters
except ImportError:
    def get_fbonly_converters():
        return []


def convert(base_path, rule):
    """
    Convert the python representation of a targets file into a python
    representation of a buck file.
    """

    converters = [
        cython.Converter(),
        python.PythonConverter('python_binary'),
        python.PythonConverter('python_unittest'),
        thrift_library.ThriftLibraryConverter(),
        sphinx.SphinxWikiConverter(),
        sphinx.SphinxManpageConverter(),
    ]

    converters += get_fbonly_converters()

    converter_map = {}
    new_converter_map = {
        'antlr3_srcs': antlr3_srcs,
        'antlr4_srcs': antlr4_srcs,
        'buck_cxx_binary': buck_cxx_binary,  # noqa F821
        'cpp_module_external': cpp_module_external,  # noqa F821
        'cxx_genrule': cxx_genrule,  # noqa F821
        'cpp_jvm_library': cpp_jvm_library,  # noqa F821
        'cpp_library_external_custom': cpp_library_external_custom,  # noqa F821
        'custom_unittest': custom_unittest,  # noqa F821
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
        'cgo_library': cgo_library,  # noqa F821
        'dewey_artifact': dewey_artifact,
        'cpp_binary_external': discard,  # noqa F821
        'haskell_genscript': discard,  # noqa F821
        'export_file': export_file,  # noqa F821
        'export_files': export_files,  # noqa F821
        'versioned_alias': versioned_alias,  # noqa F821
        'remote_file': remote_file,  # noqa F821
        'test_suite': test_suite,  # noqa F821
        'buck_command_alias': buck_command_alias,  # noqa F821
        'custom_rule': custom_rule,  # noqa F821
        'go_binary': go_binary,  # noqa F821
        'go_bindgen_library': go_bindgen_library,  # noqa F821
        'go_external_library': go_external_library,  # noqa F821
        'go_library': go_library,  # noqa F821
        'go_unittest': go_unittest,  # noqa F821
        'haskell_external_library': haskell_external_library,  # noqa F821
        'haskell_binary': haskell_binary,  # noqa F821
        'haskell_haddock': haskell_haddock,  # noqa F821
        'haskell_ghci': haskell_ghci,  # noqa F821
        'haskell_library': haskell_library,  # noqa F821
        'haskell_unittest': haskell_unittest,  # noqa F821
        'java_binary': java_binary,  # noqa F821
        'java_library': java_library,  # noqa F821
        'java_protoc_library': java_protoc_library,  # noqa F821
        'java_shaded_jar': java_shaded_jar,  # noqa F821
        'java_test': java_test,  # noqa F821
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
        'python_wheel': python_wheel,  # noqa F821
        'python_wheel_default': python_wheel_default,  # noqa F821
        'rust_binary': rust_binary,  # noqa F821
        'rust_bindgen_library': rust_bindgen_library,  # noqa F821
        'rust_external_library': rust_external_library,  # noqa F821
        'rust_library': rust_library,  # noqa F821
        'rust_unittest': rust_unittest,  # noqa F821
        'scala_library': scala_library,  # noqa F821
        'scala_test': scala_test,  # noqa F821
        'swig_library': swig_library,  # noqa F821
        'cpp_library_external': cpp_library_external,
        'cpp_benchmark': cpp_benchmark,  # noqa F821
        'cpp_lua_extension': cpp_lua_extension,  # noqa F821
        'cpp_java_extension': cpp_java_extension,  # noqa F821
        'cpp_lua_main_module': cpp_lua_main_module,  # noqa F821
        'cpp_python_extension': cpp_python_extension,  # noqa F821
        'cpp_node_extension': cpp_node_extension,  # noqa F821
        'cpp_precompiled_header': cpp_precompiled_header,  # noqa F821
        'cpp_unittest': cpp_unittest,
        'cpp_library': cpp_library,
        'cpp_binary': cpp_binary,
        'd_binary': d_binary,
        'd_library': d_library,
        'd_library_external': d_library_external,
        'd_unittest': d_unittest,
        'python_library': python_library,  # noqa F821
    }

    if image_feature:
        new_converter_map['image_feature'] = image_feature
    if image_layer:
        new_converter_map['image_layer'] = image_layer
    if image_package:
        new_converter_map['image_package'] = image_package

    for converter in converters:
        converter_map[converter.get_fbconfig_rule_type()] = converter

    converter = new_converter_map.get(rule.type, converter_map.get(rule.type))

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
