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
import operator

with allow_unsafe_import():  # noqa: magic
    from distutils.version import LooseVersion


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
load("@bazel_skylib//lib:collections.bzl", "collections")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs/lib:build_info.bzl", "build_info")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs/lib:python_typing.bzl",
     "get_typing_config_target", "gen_typing_config")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:python_common.bzl", "python_common")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs/lib:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:python_versioning.bzl", "python_versioning")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:string_macros.bzl", "string_macros")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_choice")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_list")


class PythonConverter(base.Converter):

    RULE_TYPE_MAP = {
        'python_library': 'python_library',
        'python_binary': 'python_binary',
        'python_unittest': 'python_test',
    }

    def __init__(self, rule_type):
        super(PythonConverter, self).__init__()
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self.RULE_TYPE_MAP[self._rule_type]

    def convert(
        self,
        base_path,
        name=None,
        py_version=None,
        py_flavor="",
        base_module=None,
        main_module=None,
        strip_libpar=True,
        srcs=(),
        versioned_srcs=(),
        tags=(),
        gen_srcs=(),
        deps=[],
        tests=[],
        lib_dir=None,
        par_style=None,
        emails=None,
        external_deps=[],
        needed_coverage=None,
        argcomplete=None,
        strict_tabs=None,
        compile=None,
        args=None,
        env=None,
        python=None,
        allocator=None,
        check_types=False,
        preload_deps=(),
        visibility=None,
        resources=(),
        jemalloc_conf=None,
        typing=False,
        typing_options='',
        check_types_options='',
        runtime_deps=(),
        cpp_deps=(),  # ctypes targets
        helper_deps=False,
        analyze_imports=False,
        additional_coverage_targets=[],
        version_subdirs=None,
    ):
        is_test = self.get_fbconfig_rule_type() == 'python_unittest'
        is_library = self.get_fbconfig_rule_type() == 'python_library'
        is_binary = self.get_fbconfig_rule_type() == 'python_binary'
        fbconfig_rule_type = self.get_fbconfig_rule_type()
        buck_rule_type = self.get_buck_rule_type()

        library_attributes = python_common.convert_library(
            is_test=is_test,
            is_library=is_library,
            base_path=base_path,
            name=name,
            base_module=base_module,
            check_types=check_types,
            cpp_deps=cpp_deps,
            deps=deps,
            external_deps=external_deps,
            gen_srcs=gen_srcs,
            py_flavor=py_flavor,
            resources=resources,
            runtime_deps=runtime_deps,
            srcs=srcs,
            tags=tags,
            tests=tests,
            typing=typing,
            typing_options=typing_options,
            version_subdirs=version_subdirs,
            versioned_srcs=versioned_srcs,
            visibility=visibility,
        )
        # People use -library of unittests
        fb_native.python_library(**library_attributes)

        if is_library:
            # If we are a library then we are done now
            return

        # For binary rules, create a separate library containing the sources.
        # This will be added as a dep for python binaries and merged in for
        # python tests.
        if is_list(py_version) and len(py_version) == 1:
            py_version = py_version[0]

        if not is_list(py_version):
            versions = {py_version: name}
        else:
            versions = {}
            platform = platform_utils.get_platform_for_base_path(base_path)
            for py_ver in py_version:
                python_version = python_versioning.get_default_version(platform, py_ver)
                new_name = name + '-' + python_version.version_string
                versions[py_ver] = new_name
        py_tests = []
        # There are some sub-libraries that get generated based on the
        # name of the original library, not the binary. Make sure they're only
        # generated once.
        is_first_binary = True
        for py_ver, py_name in sorted(versions.items()):
            # Turn off check types for py2 targets when py3 is in versions
            # so we can have the py3 parts type check without a separate target
            if (
                check_types
                and python_versioning.constraint_matches_major(py_ver, version=2)
                and any([
                    python_versioning.constraint_matches_major(v, version=3)
                    for v in versions
                ])
            ):
                _check_types = False
                print(
                    base_path + ':' + py_name,
                    'will not be typechecked because it is the python 2 part',
                )
            else:
                _check_types = check_types

            binary_attributes = python_common.single_binary_or_unittest(
                base_path,
                py_name,
                implicit_library_target=":" + library_attributes["name"],
                implicit_library_attributes=library_attributes,
                fbconfig_rule_type=fbconfig_rule_type,
                buck_rule_type=buck_rule_type,
                is_test=is_test,
                tests=tests,
                py_version=py_ver,
                py_flavor=py_flavor,
                main_module=main_module,
                strip_libpar=strip_libpar,
                tags=tags,
                par_style=par_style,
                emails=emails,
                needed_coverage=needed_coverage,
                argcomplete=argcomplete,
                strict_tabs=strict_tabs,
                compile=compile,
                args=args,
                env=env,
                python=python,
                allocator=allocator,
                check_types=_check_types,
                preload_deps=preload_deps,
                jemalloc_conf=jemalloc_conf,
                typing_options=check_types_options,
                helper_deps=helper_deps,
                visibility=visibility,
                analyze_imports=analyze_imports,
                additional_coverage_targets=additional_coverage_targets,
                generate_test_modules=is_first_binary,
            )
            yield Rule(buck_rule_type, binary_attributes)

            is_first_binary = False
            if is_test:
                py_tests.append(
                    (":" + binary_attributes['name'], binary_attributes.get('tests'))
                )

        # TODO: This should probably just be test_suite? This rule really doesn't
        #       make sense....
        # Create a genrule to wrap all the tests for easy running
        if len(py_tests) > 1:
            # We are propogating tests from sub targets to this target
            gen_tests = []
            for test_target, tests_attribute in py_tests:
                gen_tests.append(test_target)
                if tests_attribute:
                    gen_tests.extend(tests_attribute)
            gen_tests = collections.uniq(gen_tests)

            cmd = ' && '.join([
                'echo $(location {})'.format(test_target)
                for test_target in gen_tests
            ])

            fb_native.genrule(
                name = name,
                visibility = visibility,
                out = 'unused',
                tests = gen_tests,
                cmd = cmd,
            )
