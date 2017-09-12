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
import sys

from .convert import base
from .convert import cpp
from .convert import cpp_library_external
from .convert import cpp_library_external_custom
from .convert import custom_rule
from .convert import custom_unittest
from .convert import cython
from .convert import d
from .convert import dewey_artifact
from .convert import discard
from .convert import go
from .convert import haskell
from .convert import haskell_external_library
try:
    from .convert import java
    from .convert import java_plugins
    from .convert import javafoundations
    use_internal_java_converters = True
except ImportError:
    use_internal_java_converters = False
from .convert import js
from .convert import lua
from .convert import ocaml
from .convert import ocaml_library_external
from .convert import passthrough
from .convert import python
from .convert import rust
from .convert import rust_bindgen_library
from .convert import rust_library_external
from .convert import swig_library
from .convert import thrift_library
try:
    from .convert.facebook import get_fbonly_converters
except ImportError:
    def get_fbonly_converters(context):
        return []


FBCODE_UI_MESSAGE = (
    'Unsupported access to Buck rules! '
    'Please use supported fbcode rules (https://fburl.com/fbcode-targets) '
    'instead.')


# DO NOT MODIFY THIS LIST.  This grandfathers in some places where non-
# experimental rules depend on experimental rules and should not grow.  Please
# reach out to fbcode foundation with any questions.
EXPERIMENTAL_WHITELIST = (
    ('experimental/deeplearning', 'all_lua'),
    ('experimental/deeplearning/mobile-vision/segmentation/tools/create_coco_format_dataset/tests', 'analyze_json_lib'),
    ('experimental/deeplearning/ntt/detection_caffe2/lib', 'lib'),
    ('experimental/deeplearning/vajdap/xray', 'xray_lib'),
    ('experimental/deeplearning/vision/cluster_utils', 'io'),
    ('experimental/deeplearning/vision/cluster_utils', 'io'),
    ('experimental/deeplearning/vision/detection_caffe2/lib/fb', 'omnibus-blacklist-hack'),
    ('experimental/deeplearning/wym/classification_attribute/datasets', 'attr_data'),
    ('experimental/deeplearning/zyan3/sherlock/visual_sherlock/meter', 'classerrormeter'),
    ('experimental/deeplearning/zyan3/sherlock/visual_sherlock/meter', 'mapmeter'),
    ('experimental/everstore/orphaned_needles/WorkitemList', 'workitemlist_client_lib'),
    ('experimental/everstore/orphaned_needles/WorkitemList/if', 'workitemserver_thrift-py'),
    ('experimental/guruqu/transformers', 'segmax_predict'),
    ('experimental/pau/dummyservicewdeps', 'dummy_service_w_deps-py'),
    ('experimental/pshinghal/dummy_service', 'thrift-py'),
)


class ConversionError(Exception):
    pass


Results = collections.namedtuple('Results', ['rules', 'errors'])


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


def is_supported_platform(context, converter, pattern):
    """
    Returns False if we should pretend tha the current rule doesn't
    exist.  This is used to control whether a rule participates in
    the build for a given platform.

    For regular fbcode builds on linux the platform name will be
    something like `gcc-X.Y-glibc-A.B`.  The recommendation is that
    linux specific rules should specify:

       supported_platforms_regex='glibc'

    For the macos platform builds, we'll define the platform to be
    something like:

       clang-X.Y-macos-A.B (where A.B is the value of
         MACOSX_DEPLOYMENT_TARGET used with that platform)

    The platform name is composed with the internal vs public build
    mode.  This build mode helps to scope dependencies on things
    that are not opensourced.  The default value of the build mode
    is 'facebook' which indicates that all of fbcode is available
    to build.  The open source build will have this set to 'public'.

    This means that the fully qualified platform string, for the
    purposes of this function will typically be something like:

       gcc-X.Y-glibc-A.B-facebook
       clang-X.Y-macos-A.B-public

    The pattern match is unanchored which allows using a pattern
    like 'public' to specify public only rules, 'facebook' for
    facebook internal rules, 'glibc' for linux only rules and so on.
    """

    if pattern is None:
        # No restriction: the rule is available on all platforms
        return True

    mode_string = 'facebook'
    if context.buck_ops.read_config('fbcode', 'is_public', False):
        mode_string = 'public'
    platform = converter.get_default_platform()
    full_platform_string = '%s-%s' % (platform, mode_string)

    return re.search(pattern, full_platform_string)


def set_default_visibility(base_path, converted_rules):
    for rule in converted_rules:

        # Experimental code can only be depended on by other experimental code.
        if (base_path.split(os.sep)[0] == 'experimental' and
                (base_path, rule.attributes['name']) not in EXPERIMENTAL_WHITELIST):
            rule.attributes['visibility'] = ['//experimental/...']

        # Make sure we don't override previous visibility
        rule.attributes.setdefault('visibility', ['PUBLIC'])

        yield rule


def convert(context, base_path, rules):
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
        cython.Converter(context),
        d.DConverter(context, 'd_binary'),
        d.DConverter(context, 'd_library'),
        d.DConverter(context, 'd_unittest', 'd_test'),
        dewey_artifact.DeweyArtifactConverter(context),
        go.GoConverter(context, 'go_binary'),
        go.GoConverter(context, 'go_library'),
        go.GoConverter(context, 'go_unittest', 'go_test'),
        haskell.HaskellConverter(context, 'haskell_binary'),
        haskell.HaskellConverter(context, 'haskell_library'),
        haskell.HaskellConverter(context, 'haskell_unittest', 'haskell_binary'),
        haskell.HaskellConverter(context, 'haskell_ghci'),
        haskell.HaskellConverter(context, 'haskell_haddock'),
        haskell_external_library.HaskellExternalLibraryConverter(context),
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
        passthrough.PassthroughConverter(
            context,
            'export_file',
            'export_file',
            {'mode': 'reference'}),
        passthrough.PassthroughConverter(
            context,
            'versioned_alias',
            'versioned_alias'),
        passthrough.PassthroughConverter(
            context,
            'remote_file',
            'remote_file'),
        passthrough.PassthroughConverter(
            context,
            'buck_command_alias',
            'command_alias',
            convert_targets_on=['exe']),
    ]
    if use_internal_java_converters:
        converters += [
            java.JavaLibraryConverter(context),
            java.JavaBinaryConverter(context),
            java_plugins.JarShadeConverter(context),
            java.JavaTestConverter(context),
            javafoundations.PrebuiltJarConverter(
                context,
                passthrough.PassthroughConverter(
                    context,
                    'prebuilt_jar',
                    'prebuilt_jar')),
        ]

    converters += get_fbonly_converters(context)

    # Passthrough support for fbconfig rules prefixed with "buck_".
    if use_internal_java_converters:
        converters += [
            java.JavaBinaryConverter(context, 'buck_java_binary'),
            java.JavaLibraryConverter(context, 'buck_java_library'),
            java.JavaTestConverter(context, 'buck_java_test'),
            javafoundations.PrebuiltJarConverter(
                context,
                passthrough.PassthroughConverter(
                    context,
                    'buck_prebuilt_jar',
                    'prebuilt_jar'))
        ]
    converters.append(
        passthrough.PassthroughConverter(
            context,
            'buck_cxx_binary',
            'cxx_binary',
            # DO NOT ADD TO THIS WHITELIST! (#15633732).
            whitelist=context.config.whitelisted_raw_buck_rules.get('cxx_binary', []),
            whitelist_error_msg=FBCODE_UI_MESSAGE))
    converters.append(
        passthrough.PassthroughConverter(
            context,
            'buck_cxx_library',
            'cxx_library',
            # DO NOT ADD TO THIS WHITELIST! (#15633732).
            whitelist=context.config.whitelisted_raw_buck_rules.get('cxx_library', []),
            whitelist_error_msg=FBCODE_UI_MESSAGE))
    converters.append(
        passthrough.PassthroughConverter(
            context,
            'buck_cxx_test',
            'cxx_test',
            # DO NOT ADD TO THIS WHITELIST! (#15633732).
            whitelist=context.config.whitelisted_raw_buck_rules.get('cxx_test', []),
            whitelist_error_msg=FBCODE_UI_MESSAGE))
    converters.append(
        passthrough.PassthroughConverter(
            context,
            'cxx_genrule',
            'cxx_genrule',
        ))
    for buck_rule in (
            'export_file',
            'genrule',
            'project_config',
            'python_binary',
            'python_library',
            'sh_binary',
            'sh_test'):
        converters.append(
            passthrough.PassthroughConverter(
                context,
                'buck_' + buck_rule,
                buck_rule))

    converter_map = {}

    for converter in converters:
        converter_map[converter.get_fbconfig_rule_type()] = converter

    results = []
    errors = {}

    for rule in rules:

        if rule.type not in converter_map:
            name = '{0}:{1}'.format(base_path, rule.attributes['name'])
            raise ValueError('unknown rule type ' + rule.type)

        pattern = rule.attributes.pop('supported_platforms_regex', None)
        if not is_supported_platform(context, converter_map[rule.type], pattern):
            # Elide this rule as it is not applicable in the current environment
            continue

        # Verify arguments.
        allowed_args = converter_map[rule.type].get_allowed_args()
        if allowed_args is not None:
            for attribute in rule.attributes:
                if attribute not in allowed_args:
                    raise TypeError(
                        '{}() got an unexpected keyword argument: {!r}'
                        .format(rule.type, attribute))

        try:
            results.extend(   # Supports generators
                set_default_visibility(
                    base_path,
                    converter_map[rule.type].convert(
                        base_path,
                        **rule.attributes
                    ),
                )
            )
        except base.RuleError as e:
            name = '{0}:{1}'.format(base_path, rule.attributes['name'])
            errors[name] = str(e)
            continue

    return Results(results, errors)
