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

    def get_languages(self, names):
        """
        Convert the `languages` parameter to a normalized list of languages.
        """

        languages = {}

        if names == None:
            fail('thrift_library() requires languages argument')

        for name in names:
            lang = NAMES_TO_LANG.get(name)
            if lang == None:
                fail('thrift_library() does not support language {}'.format(name))
            if lang in languages:
                fail('thrift_library() given duplicate language {}'.format(lang))
            languages[lang] = None

        return languages


    def generate_compile_rule(
            self,
            base_path,
            name,
            compiler,
            lang,
            compiler_args,
            source,
            postprocess_cmd=None,
            visibility=None):
        """
        Generate a rule which runs the thrift compiler for the given inputs.
        """

        genrule_name = (
            '{}-{}-{}'.format(name, lang, src_and_dep_helpers.get_source_name(source)))
        cmds = []
        converter = CONVERTERS[lang]
        cmds.append(
            converter.get_compiler_command(
                compiler,
                compiler_args,
                get_exported_include_tree(':' + name),
                converter.get_additional_compiler()))

        if postprocess_cmd != None:
            cmds.append(postprocess_cmd)

        fb_native.genrule(
            name = genrule_name,
            labels = ['generated'],
            visibility = visibility,
            out = common_paths.CURRENT_DIRECTORY,
            srcs = [source],
            cmd = ' && '.join(cmds),
        )
        return genrule_name

    def generate_generated_source_rules(self, compile_name, srcs, visibility):
        """
        Create rules to extra individual sources out of the directory of thrift
        sources the compiler generated.
        """

        out = {}
        rules = []

        for name, src in srcs.items():
            cmd = ' && '.join([
                'mkdir -p `dirname $OUT`',
                'cp -R $(location :{})/{} $OUT'.format(compile_name, src),
            ])
            genrule_name = '{}={}'.format(compile_name, src)
            fb_native.genrule(
                name = genrule_name,
                labels = ['generated'],
                visibility = visibility,
                out = src,
                cmd = cmd,
            )
            out[name] = ':' + genrule_name

        return out

    def convert_macros(
            self,
            base_path,
            name,
            thrift_srcs={},
            thrift_args=(),
            deps=(),
            external_deps=(),
            languages=None,
            visibility=None,
            plugins=[],
            **kwargs):
        """
        Thrift library conversion implemented purely via macros (i.e. no Buck
        support).
        """

        # Parse incoming options.
        # TODO: These are top level attributes, move them to convert() when we get
        # rid of `kwargs at the top level over convert()`
        thrift_srcs = fixup_thrift_srcs(thrift_srcs)
        thrift_args = parse_thrift_args(thrift_args)
        languages = self.get_languages(languages)
        deps = [src_and_dep_helpers.convert_build_target(base_path, d) for d in deps]

        # Setup the exported include tree to dependents.
        includes = []
        includes.extend(thrift_srcs.keys())
        for lang in languages:
            converter = CONVERTERS[lang]
            includes.extend(converter.get_extra_includes(**kwargs))

        merge_tree(
            base_path,
            get_exported_include_tree(name),
            sorted(collections.uniq(includes)),
            [get_exported_include_tree(dep) for dep in deps],
            labels=["generated"],
            visibility=visibility)

        # py3 thrift requires cpp2
        if 'py3' in languages and 'cpp2' not in languages:
            languages['cpp2'] = None

        # save cpp2_options for later use by 'py3'
        if 'cpp2' in languages:
            cpp2_options = (
                parse_thrift_options(
                    kwargs.get('thrift_cpp2_options', ())))

        # Types are generated for all legacy Python Thrift
        if 'py' in languages:
            languages['pyi'] = None
            # Save the options for pyi to use
            py_options = (parse_thrift_options(
                kwargs.get('thrift_py_options', ())
            ))

        if 'py-asyncio' in languages:
            languages['pyi-asyncio'] = None
            # Save the options for pyi to use
            py_asyncio_options = (parse_thrift_options(
                kwargs.get('thrift_py_asyncio_options', ())
            ))

        # Generate rules for all supported languages.
        for lang in languages:
            converter = CONVERTERS[lang]
            compiler = converter.get_compiler()
            options = (
                parse_thrift_options(
                    kwargs.get('thrift_{}_options'.format(
                        lang.replace('-', '_')), ())))
            if lang == "pyi":
                options.update(py_options)
            if lang == "pyi-asyncio":
                options.update(py_asyncio_options)
            if lang == 'py3':
                options.update(cpp2_options)

            compiler_args = converter.get_compiler_args(
                converter.get_compiler_lang(),
                thrift_args,
                converter.get_options(base_path, options),
                **kwargs)

            all_gen_srcs = {}
            for thrift_src, services in thrift_srcs.items():
                thrift_name = src_and_dep_helpers.get_source_name(thrift_src)

                # Generate the thrift compile rules.
                compile_rule_name = (
                    self.generate_compile_rule(
                        base_path,
                        name,
                        compiler,
                        lang,
                        compiler_args,
                        thrift_src,
                        converter.get_postprocess_command(
                            base_path,
                            thrift_name,
                            '$OUT',
                            **kwargs),
                        visibility=visibility))

                # Create wrapper rules to extract individual generated sources
                # and expose via target refs in the UI.
                gen_srcs = (
                    converter.get_generated_sources(
                        base_path,
                        name,
                        thrift_name,
                        services,
                        options,
                        visibility=visibility,
                        **kwargs))
                gen_srcs = self.generate_generated_source_rules(
                    compile_rule_name,
                    gen_srcs,
                    visibility=visibility
                )
                all_gen_srcs[thrift_name] = gen_srcs

            # Generate rules from Thrift plugins
            for plugin in plugins:
                plugin.generate_rules(
                    plugin,
                    base_path,
                    name,
                    lang,
                    thrift_srcs,
                    compiler_args,
                    get_exported_include_tree(':' + name),
                    deps,
                )
            # Generate the per-language rules.
            converter.get_language_rule(
                base_path,
                name + '-' + lang,
                thrift_srcs,
                options,
                all_gen_srcs,
                [dep + '-' + lang for dep in deps],
                visibility=visibility,
                **kwargs)

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

    def convert(self, base_path, name=None, languages=None, visibility=None, **kwargs):
        visibility = get_visibility(visibility, name)

        supported_languages = read_list(
            'thrift', 'supported_languages', delimiter=None, required=False,
        )
        if supported_languages != None:
            languages = sets.to_list(
                sets.intersection(
                    sets.make(languages), sets.make(supported_languages)))

        # Convert rules we support via macros.
        macro_languages = self.get_languages(languages)
        if macro_languages:
            self.convert_macros(base_path, name=name, languages=languages, visibility=visibility, **kwargs)

        # If python is listed in languages, then also generate the py-remote
        # rules.
        # TODO: Move this logic into convert_macros
        if 'py' in languages or 'python' in languages:
            py_remote_binaries(
                base_path,
                name=name,
                thrift_srcs=fixup_thrift_srcs(kwargs.get('thrift_srcs', {})),
                base_module=kwargs.get('py_base_module'),
                include_sr=kwargs.get('py_remote_service_router', False),
                visibility=visibility)

        return []
