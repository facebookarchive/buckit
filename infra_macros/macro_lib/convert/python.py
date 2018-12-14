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

    def create_binary(
        self,
        base_path,
        name,
        implicit_library_target,
        implicit_library_attributes,
        fbconfig_rule_type,
        is_test,
        tests=[],
        py_version=None,
        py_flavor="",
        main_module=None,
        rule_type=None,
        strip_libpar=True,
        tags=(),
        lib_dir=None,
        par_style=None,
        emails=None,
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
        jemalloc_conf=None,  # TODO: This does not appear to be used anywhere
        typing_options='',
        helper_deps=False,
        visibility=None,
        analyze_imports=False,
        additional_coverage_targets=[],
        generate_test_modules=False,
    ):
        if is_test and par_style == None:
            par_style = "xar"
        rules = []
        dependencies = []
        platform_deps = []
        out_preload_deps = []
        platform = platform_utils.get_platform_for_base_path(base_path)
        python_version = python_versioning.get_default_version(platform=platform,
                                                  constraint=py_version,
                                                  flavor=py_flavor)
        if python_version is None:
            fail((
                "Unable to find Python version matching constraint" +
                "'{}' and flavor '{}' on '{}'.").format(py_version, py_flavor, platform)
            )

        python_platform = platform_utils.get_buck_python_platform(platform,
                                                   major_version=python_version.major,
                                                   flavor=py_flavor)

        if allocator == None:
            allocator = allocators.normalize_allocator(allocator)

        attributes = collections.OrderedDict()
        attributes['name'] = name
        if is_test and additional_coverage_targets:
            attributes["additional_coverage_targets"] = additional_coverage_targets
        if visibility != None:
            attributes['visibility'] = visibility

        if not rule_type:
            rule_type = self.get_buck_rule_type()

        # If this is a test, we need to merge the library rule into this
        # one and inherit its deps.
        if is_test:
            for param in ('versioned_srcs', 'srcs', 'resources', 'base_module'):
                val = implicit_library_attributes.get(param)
                if val != None:
                    attributes[param] = val
            dependencies.extend(implicit_library_attributes.get('deps', []))
            platform_deps.extend(implicit_library_attributes.get('platform_deps', []))

            # Add the "coverage" library as a dependency for all python tests.
            platform_deps.extend(
                src_and_dep_helpers.format_platform_deps(
                    [target_utils.ThirdPartyRuleTarget('coverage', 'coverage-py')]))

        # Otherwise, this is a binary, so just the library portion as a dep.
        else:
            dependencies.append(':' + implicit_library_attributes['name'])

        # Sanitize the main module, so that it's a proper module reference.
        if main_module != None:
            main_module = main_module.replace('/', '.')
            if main_module.endswith('.py'):
                main_module = main_module[:-3]
            attributes['main_module'] = main_module
        elif is_test:
            main_module = '__fb_test_main__'
            attributes['main_module'] = main_module

        # Add in the PAR build args.
        if python_common.get_package_style() == 'standalone':
            build_args = (
                python_common.get_par_build_args(
                    base_path,
                    name,
                    rule_type,
                    platform,
                    argcomplete=argcomplete,
                    strict_tabs=strict_tabs,
                    compile=compile,
                    par_style=par_style,
                    strip_libpar=strip_libpar,
                    needed_coverage=needed_coverage,
                    python=python))
            if build_args:
                attributes['build_args'] = build_args

        # Add any special preload deps.
        default_preload_deps = (
            python_common.preload_deps(base_path, name, allocator, jemalloc_conf, visibility))
        out_preload_deps.extend(src_and_dep_helpers.format_deps(default_preload_deps))

        # Add user-provided preloaded deps.
        for dep in preload_deps:
            out_preload_deps.append(src_and_dep_helpers.convert_build_target(base_path, dep))

        # Add the C/C++ build info lib to preload deps.
        cxx_build_info = cpp_common.cxx_build_info_rule(
            base_path,
            name,
            fbconfig_rule_type,
            platform,
            static=False,
            visibility=visibility)
        out_preload_deps.append(target_utils.target_to_label(cxx_build_info))

        # Provide a standard set of backport deps to all binaries
        platform_deps.extend(
            src_and_dep_helpers.format_platform_deps(
                [target_utils.ThirdPartyRuleTarget('typing', 'typing-py'),
                 target_utils.ThirdPartyRuleTarget('python-future', 'python-future-py')]))

        # Provide a hook for the nuclide debugger in @mode/dev builds, so
        # that one can have `PYTHONBREAKPOINT=nuclide.set_trace` in their
        # environment (eg .bashrc) and then simply write `breakpoint()`
        # to launch a debugger with no fuss
        if python_common.get_package_style() == "inplace":
            dependencies.append("//nuclide:debugger-hook")

        # Add in a specialized manifest when building inplace binaries.
        #
        # TODO(#11765906):  We shouldn't need to create this manifest rule for
        # standalone binaries.  However, since target determinator runs in dev
        # mode, we sometimes pass these manifest targets in the explicit target
        # list into `opt` builds, which then fails with a missing build target
        # error.  So, for now, just always generate the manifest library, but
        # only use it when building inplace binaries.
        manifest_name = python_common.manifest_library(
            base_path,
            name,
            fbconfig_rule_type,
            main_module,
            platform,
            python_platform,
            visibility,
        )
        if python_common.get_package_style() == 'inplace':
            dependencies.append(':' + manifest_name)

        buck_cxx_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        attributes['cxx_platform'] = buck_cxx_platform
        attributes['platform'] = python_platform
        attributes['version_universe'] = python_common.get_version_universe(python_version)
        attributes['linker_flags'] = (
            python_common.get_ldflags(base_path, name, fbconfig_rule_type, strip_libpar=strip_libpar))

        attributes['labels'] = list(tags)
        if is_test:
            attributes['labels'].extend(label_utils.convert_labels(platform, 'python'))

        attributes['tests'] = tests

        if args:
            attributes['args'] = (
                string_macros.convert_args_with_macros(
                    base_path,
                    args,
                    platform=platform))

        if env:
            attributes['env'] = (
                string_macros.convert_env_with_macros(
                    env,
                    platform=platform))

        if emails:
            attributes['contacts'] = emails

        if out_preload_deps:
            attributes['preload_deps'] = out_preload_deps

        if needed_coverage:
            attributes['needed_coverage'] = [
                python_common.convert_needed_coverage_spec(base_path, s)
                for s in needed_coverage
            ]

        # Generate the interpreter helpers, and add them to our deps. Note that
        # we must do this last, so that the interp rules get the same deps as
        # the main binary which we've built up to this point.
        # We also do this based on an attribute so that we don't have to dedupe
        # rule creation. We'll revisit this in the near future.
        # TODO: Better way to not generate duplicates
        if python_common.should_generate_interp_rules(helper_deps):
            interp_deps = list(dependencies)
            if is_test:
                testmodules_library_name = python_common.test_modules_library(
                    base_path,
                    implicit_library_attributes['name'],
                    implicit_library_attributes.get('srcs') or (),
                    implicit_library_attributes.get('base_module'),
                    visibility,
                    generate_test_modules = generate_test_modules,
                )
                interp_deps.append(':' + testmodules_library_name)
            interp_rules = python_common.interpreter_binaries(
                name,
                buck_cxx_platform,
                python_version,
                python_platform,
                interp_deps,
                platform_deps,
                out_preload_deps,
                visibility,
            )
            dependencies.extend([':' + interp_rule for interp_rule in interp_rules])
        if check_types:
            if python_version.major != 3:
                fail('parameter `check_types` is only supported on Python 3.')
            typecheck_rule_name = python_common.typecheck_test(
                name,
                main_module,
                buck_cxx_platform,
                python_platform,
                python_version,
                dependencies,
                platform_deps,
                out_preload_deps,
                typing_options,
                visibility,
                emails,
                implicit_library_target,
                implicit_library_attributes.get('versioned_srcs'),
                implicit_library_attributes.get('srcs'),
                implicit_library_attributes.get('resources'),
                implicit_library_attributes.get('base_module'),
            )
            attributes['tests'] = (
                list(attributes['tests']) + [':' + typecheck_rule_name]
            )
        if analyze_imports:
            python_common.analyze_import_binary(
                name,
                buck_cxx_platform,
                python_platform,
                python_version,
                dependencies,
                platform_deps,
                out_preload_deps,
                visibility
            )
        if is_test:
            if not dependencies:
                dependencies = []
            dependencies.append('//python:fbtestmain')

        if dependencies:
            attributes['deps'] = dependencies

        if platform_deps:
            attributes['platform_deps'] = platform_deps

        if (
            read_bool('fbcode', 'monkeytype', False) and
            python_version.major == 3
        ):
            python_common.monkeytype_binary(rule_type, attributes, implicit_library_attributes['name'])

        return [Rule(rule_type, attributes)] + rules

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
        if isinstance(py_version, list) and len(py_version) == 1:
            py_version = py_version[0]

        if not isinstance(py_version, list):
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
                and any(python_versioning.constraint_matches_major(v, version=3) for v in versions)
            ):
                _check_types = False
                print(
                    base_path + ':' + py_name,
                    'will not be typechecked because it is the python 2 part',
                )
            else:
                _check_types = check_types

            rules = self.create_binary(
                base_path,
                py_name,
                implicit_library_target=":" + library_attributes["name"],
                implicit_library_attributes=library_attributes,
                fbconfig_rule_type=fbconfig_rule_type,
                is_test=is_test,
                tests=tests,
                py_version=py_ver,
                py_flavor=py_flavor,
                main_module=main_module,
                strip_libpar=strip_libpar,
                tags=tags,
                lib_dir=lib_dir,
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
            is_first_binary = False
            if is_test:
                py_tests.append(rules[0])
            for rule in rules:
                yield rule

        # Create a genrule to wrap all the tests for easy running
        if len(py_tests) > 1:
            attrs = collections.OrderedDict()
            attrs['name'] = name
            if visibility != None:
                attrs['visibility'] = visibility
            attrs['out'] = '.' # TODO: This should be a real directory
            # We are propogating tests from sub targets to this target
            gen_tests = set()
            for r in py_tests:
                gen_tests.add(r.target_name)
                if 'tests' in r.attributes:
                    gen_tests.update(r.attributes['tests'])
            attrs['tests'] = sorted(list(gen_tests))
            # With this we are telling buck we depend on the test targets
            cmds = []
            for test in py_tests:
                cmds.append('echo $(location {})'.format(test.target_name))
            attrs['cmd'] = ' && '.join(cmds)
            yield Rule('genrule', attrs)
