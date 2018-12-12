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
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:merge_tree.bzl", "merge_tree")
load("@fbcode_macros//build_defs/lib:copy_rule.bzl", "copy_rule")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load(
    "@fbsource//tools/build_defs:fb_native_wrapper.bzl",
    "fb_native",
)
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs/lib/swig:go_converter.bzl", "go_converter")
load("@fbcode_macros//build_defs/lib/swig:java_converter.bzl", "java_converter")
load("@fbcode_macros//build_defs/lib/swig:python_converter.bzl", "python_converter")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@bazel_skylib//lib:paths.bzl", "paths")


FLAGS = [
    '-c++',
    '-Werror',
    '-Wextra',
]


class SwigLibraryConverter(base.Converter):

    def __init__(self, *args, **kwargs):
        super(SwigLibraryConverter, self).__init__(*args, **kwargs)

        # Setup the macro converters.
        converters = [
            java_converter,
            go_converter,
            python_converter,
        ]
        self._converters = {c.get_lang(): c for c in converters}

    def get_fbconfig_rule_type(self):
        return 'swig_library'

    def get_languages(self, langs):
        """
        Convert the `languages` parameter to a normalized list of languages.
        """

        languages = set()

        if langs is None:
            raise TypeError('swig_library() requires `languages` argument')

        if not langs:
            raise TypeError('swig_library() requires at least on language')

        for lang in langs:
            if lang not in self._converters:
                raise TypeError(
                    'swig_library() does not support language {!r}'
                    .format(lang))
            if lang in languages:
                raise TypeError(
                    'swig_library() given duplicate language {!r}'
                    .format(lang))
            languages.add(lang)

        return languages

    def get_exported_include_tree(self, dep):
        """
        Generate the exported swig source includes target use for the given
        swig library target.
        """

        return dep + '-swig-includes'

    def generate_compile_rule(
            self,
            base_path,
            name,
            swig_flags,
            lang,
            interface,
            cpp_deps,
            visibility,
            **kwargs):
        """
        Generate a rule which runs the swig compiler for the given inputs.
        """

        rules = []

        platform = platform_utils.get_platform_for_base_path(base_path)
        converter = self._converters[lang]
        base, _ = paths.split_extension(src_and_dep_helpers.get_source_name(interface))
        hdr = base + '.h'
        src = base + '.cc'

        flags = []
        flags.extend(FLAGS)
        flags.extend(swig_flags)
        flags.extend(converter.get_lang_flags(**kwargs))

        gen_name = '{}-{}-gen'.format(name, lang)
        cmds = [
            'mkdir -p'
            ' "$OUT"/lang'
            ' \\$(dirname "$OUT"/gen/{src})'
            ' \\$(dirname "$OUT"/gen/{hdr})',
            'export PPFLAGS=(`'
            ' $(exe //tools/build/buck:swig_pp_filter)'
            ' $(cxxppflags{deps})`)',
            'touch "$OUT"/gen/{hdr}',
            '$(exe {swig}) {flags} {lang}'
            ' -I- -I$(location {includes})'
            ' "${{PPFLAGS[@]}}"'
            ' -outdir "$OUT"/lang -o "$OUT"/gen/{src} -oh "$OUT"/gen/{hdr}'
            ' "$SRCS"',
        ]
        fb_native.cxx_genrule(
            name=gen_name,
            visibility=get_visibility(visibility, gen_name),
            out=common_paths.CURRENT_DIRECTORY,
            srcs=[interface],
            cmd=(
                ' && '.join(cmds).format(
                    swig=third_party.get_tool_target('swig', None, 'bin/swig', platform),
                    flags=' '.join(map(shell.quote, flags)),
                    lang=shell.quote(converter.get_lang_opt()),
                    includes=self.get_exported_include_tree(':' + name),
                    deps=''.join([' ' + d for d in src_and_dep_helpers.format_deps(cpp_deps)]),
                    hdr=shell.quote(hdr),
                    src=shell.quote(src))),
        )

        gen_hdr_name = gen_name + '=' + hdr
        copy_rule(
            '$(location :{})/gen/{}'.format(gen_name, hdr),
            gen_hdr_name,
            hdr,
            propagate_versions=True)

        gen_src_name = gen_name + '=' + src
        copy_rule(
            '$(location :{})/gen/{}'.format(gen_name, src),
            gen_src_name,
            src,
            propagate_versions=True)

        return (
            ':{}'.format(gen_name),
            ':' + gen_hdr_name,
            ':' + gen_src_name, rules)

    def generate_generated_source_rules(self, name, src_name, srcs, visibility):
        """
        Create rules to extra individual sources out of the directory of swig
        sources the compiler generated.
        """

        out = {}
        rules = []

        for sname, src in srcs.items():
            gen_name = '{}={}'.format(name, src)
            fb_native.cxx_genrule(
                name=gen_name,
                visibility=get_visibility(visibility, gen_name),
                out=src,
                cmd=' && '.join([
                    'mkdir -p `dirname $OUT`',
                    'cp -rd $(location {})/lang/{} $OUT'.format(src_name, src),
                ]),
            )
            out[sname] = ':' + gen_name

        return out, rules

    def convert_macros(
            self,
            base_path,
            name,
            interface,
            module=None,
            languages=(),
            swig_flags=(),
            cpp_deps=(),
            ext_deps=(),
            ext_external_deps=(),
            deps=(),
            visibility=None,
            **kwargs):
        """
        Swig library conversion implemented purely via macros (i.e. no Buck
        support).
        """

        rules = []

        # Parse incoming options.
        languages = self.get_languages(languages)
        cpp_deps = [target_utils.parse_target(d, default_base_path=base_path) for d in cpp_deps]
        ext_deps = (
            [target_utils.parse_target(d, default_base_path=base_path) for d in ext_deps] +
            [src_and_dep_helpers.normalize_external_dep(d) for d in ext_external_deps])

        if module is None:
            module = name

        # Setup the exported include tree to dependents.
        merge_tree(
            base_path,
            self.get_exported_include_tree(name),
            [interface],
            map(self.get_exported_include_tree, deps),
            visibility=visibility)

        # Generate rules for all supported languages.
        for lang in languages:
            converter = self._converters[lang]

            # Generate the swig compile rules.
            compile_rule, hdr, src, extra_rules = (
                self.generate_compile_rule(
                    base_path,
                    name,
                    swig_flags,
                    lang,
                    interface,
                    cpp_deps,
                    visibility=visibility,
                    **kwargs))
            rules.extend(extra_rules)

            # Create wrapper rules to extract individual generated sources
            # and expose via target refs in the UI.
            gen_srcs = converter.get_generated_sources(module)
            gen_srcs, gen_src_rules = (
                self.generate_generated_source_rules(
                    '{}-{}-src'.format(name, lang),
                    compile_rule,
                    gen_srcs,
                    visibility=visibility))
            rules.extend(gen_src_rules)

            # Generate the per-language rules.
            rules.extend(
                converter.get_language_rule(
                    base_path,
                    name + '-' + lang,
                    module,
                    hdr,
                    src,
                    gen_srcs,
                    sorted(set(cpp_deps + ext_deps)),
                    [dep + '-' + lang for dep in deps],
                    visibility=visibility,
                    **kwargs))

        return rules

    def get_allowed_args(self):
        """
        Return the list of allowed arguments.
        """

        allowed_args = {
            'cpp_deps',
            'ext_deps',
            'ext_external_deps',
            'deps',
            'interface',
            'java_library_name',
            'java_link_style',
            'java_package',
            'languages',
            'module',
            'name',
            'py_base_module',
            'go_package_name',
            'swig_flags',
        }

        return allowed_args

    def convert(self, base_path, name=None, visibility=None, **kwargs):
        rules = []

        # Convert rules we support via macros.
        macro_languages = self.get_languages(kwargs.get('languages'))
        if macro_languages:
            rules.extend(self.convert_macros(base_path, name=name, visibility=visibility, **kwargs))

        return rules
