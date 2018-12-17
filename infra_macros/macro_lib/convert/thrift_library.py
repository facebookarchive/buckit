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
load("@fbcode_macros//build_defs/lib/thrift:d.bzl", "d_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:ocaml.bzl", "ocaml_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:rust.bzl", "rust_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:swift.bzl", "swift_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:java.bzl", "java_deprecated_thrift_converter", "java_deprecated_apache_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:cpp2.bzl", "cpp2_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:cpp2.bzl", "cpp2_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:haskell.bzl", "haskell_deprecated_thrift_converter", "haskell_hs2_thrift_converter")

load("@fbcode_macros//build_defs/lib/thrift:js.bzl", "js_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:python3.bzl", "python3_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:thriftdoc_python.bzl", "thriftdoc_python_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:go.bzl", "go_thrift_converter")
load("@fbcode_macros//build_defs:thrift_library.bzl", "py_remote_binaries")
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")



class ThriftLangConverter(base.Converter):
    """
    Base class for language-specific converters.  New languages should
    subclass this class.
    """


    def get_compiler(self):
        """
        Return which thrift compiler to use.
        """

        return thrift_interface.default_get_compiler()

    def get_lang(self):
        """
        Return the language name.
        """

        raise NotImplementedError()

    def get_names(self):
        """
        Reports all languages from this converter as a frozen set.
        """
        return frozenset([self.get_lang()])

    def get_compiler_lang(self):
        """
        Return the thrift compiler language name.
        """

        return self.get_lang()

    def get_extra_includes(self, **kwargs):
        """
        Return any additional files that should be included in the exported
        thrift compiler include tree.
        """

        return thrift_interface.default_get_extra_includes(**kwargs)

    def get_postprocess_command(
            self,
            base_path,
            thrift_src,
            out_dir,
            **kwargs):
        """
        Return an additional command to run after the compiler has completed.
        Useful for adding language-specific error checking.
        """

        return thrift_interface.default_get_postprocess_command(base_path, thrift_src, out_dir, **kwargs)

    def get_additional_compiler(self):
        """
        Target of additional compiler that should be provided to the thrift1
        compiler (or None)
        """

        return thrift_interface.default_get_additional_compiler()

    def get_compiler_args(
            self,
            compiler_lang,
            flags,
            options,
            **kwargs):
        """
        Return args to pass into the compiler when generating sources.
        """

        return thrift_interface.default_get_compiler_args(compiler_lang, flags, options, **kwargs)

    def get_compiler_command(
            self,
            compiler,
            compiler_args,
            includes,
            additional_compiler):
        return thrift_interface.default_get_compiler_command(
            compiler,
            compiler_args,
            includes,
            additional_compiler,
        )

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):
        """
        Return a dict of all generated thrift sources, mapping the logical
        language-specific name to the path of the generated source relative
        to the thrift compiler output directory.
        """

        raise NotImplementedError()

    def get_options(self, base_path, parsed_options):
        """
        Apply any conversions to parsed language-specific thrift options.
        """

        return thrift_interface.default_get_options(base_path, parsed_options)

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources,
            deps,
            visibility,
            **kwargs):
        """
        Generate the language-specific library rule (and any extra necessary
        rules).
        """

        raise NotImplementedError()


class LegacyPythonThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating Python libraries from thrift sources.
    """

    NORMAL = 'normal'
    TWISTED = 'twisted'
    ASYNCIO = 'asyncio'
    PYI = 'pyi'
    PYI_ASYNCIO = 'pyi-asyncio'

    THRIFT_PY_LIB_RULE_NAME = target_utils.RootRuleTarget('thrift/lib/py', 'py')
    THRIFT_PY_TWISTED_LIB_RULE_NAME = target_utils.RootRuleTarget('thrift/lib/py', 'twisted')
    THRIFT_PY_ASYNCIO_LIB_RULE_NAME = target_utils.RootRuleTarget('thrift/lib/py', 'asyncio')

    def __init__(self, *args, **kwargs):
        flavor = kwargs.pop('flavor', self.NORMAL)
        super(LegacyPythonThriftConverter, self).__init__(
            *args,
            **kwargs
        )
        self._flavor = flavor
        self._ext = '.py' if flavor not in (self.PYI, self.PYI_ASYNCIO) else '.pyi'

    def get_name(self, flavor, prefix, sep, base_module=False):
        if flavor in (self.PYI, self.PYI_ASYNCIO):
            if not base_module:
                return flavor
            else:
                if flavor == self.PYI_ASYNCIO:
                    flavor = self.ASYNCIO
                else:
                    flavor = self.NORMAL

        if flavor in (self.TWISTED, self.ASYNCIO):
            prefix += sep + flavor
        return prefix

    def get_names(self):
        return self._get_names(self._flavor)

    def _get_names(self, flavor):
        return frozenset([
            self.get_name(flavor, 'py', '-'),
            self.get_name(flavor, 'python', '-')])

    def get_lang(self, prefix='py'):
        return self._get_lang(self._flavor, prefix)

    def _get_lang(self, flavor, prefix='py'):
        return self.get_name(flavor, 'py', '-')

    def get_compiler_lang(self):
        return self._get_compiler_lang(self._flavor)

    def _get_compiler_lang(self, flavor):
        if flavor in (self.PYI, self.PYI_ASYNCIO):
            return 'mstch_pyi'
        return 'py'

    def get_thrift_base(self, thrift_src):
        return paths.split_extension(paths.basename(thrift_src))[0]

    def get_base_module(self, flavor, **kwargs):
        """
        Get the user-specified base-module set in via the parameter in the
        `thrift_library()`.
        """

        base_module = kwargs.get(
            self.get_name(flavor,'py', '_', base_module=True) + '_base_module')

        # If no asyncio/twisted specific base module parameter is present,
        # fallback to using the general `py_base_module` parameter.
        if base_module == None:
            base_module = kwargs.get('py_base_module')

        # If nothing is set, just return `None`.
        if base_module == None:
            return None

        # Otherwise, since we accept pathy base modules, normalize it to look
        # like a proper module.
        return '/'.join(base_module.split('.'))

    def get_thrift_dir(self, base_path, thrift_src, flavor, **kwargs):
        thrift_base = self.get_thrift_base(thrift_src)
        base_module = self.get_base_module(flavor, **kwargs)
        if base_module == None:
            base_module = base_path
        return paths.join(base_module, thrift_base)

    def get_postprocess_command(
            self,
            base_path,
            thrift_src,
            out_dir,
            **kwargs):
        return self._get_postprocess_command(base_path, thrift_src, out_dir, flavor=self._flavor, ext=self._ext, **kwargs)

    def _get_postprocess_command(
            self,
            base_path,
            thrift_src,
            out_dir,
            flavor,
            ext,
            **kwargs):

        # The location of the generated thrift files depends on the value of
        # the "namespace py" directive in the .thrift file, and we
        # unfortunately don't know what this value is.  After compilation, make
        # sure the ttypes.py file exists in the location we expect.  If not,
        # there is probably a mismatch between the base_module parameter in the
        # TARGETS file and the "namespace py" directive in the .thrift file.
        thrift_base = self.get_thrift_base(thrift_src)
        thrift_dir = self.get_thrift_dir(base_path, thrift_src, flavor, **kwargs)

        output_dir = paths.join(out_dir, 'gen-py', thrift_dir)
        ttypes_path = paths.join(output_dir, 'ttypes' + ext)

        msg = [
            'Compiling %s did not generate source in %s'
            % (paths.join(base_path, thrift_src), ttypes_path)
        ]
        if flavor == self.ASYNCIO or flavor == self.PYI_ASYNCIO:
            py_flavor = 'py.asyncio'
        elif flavor == self.TWISTED:
            py_flavor = 'py.twisted'
        else:
            py_flavor = 'py'
        # TODO: Just turn this into one large error string and use proper formatters
        msg.append(
            'Does the "\\"namespace %s\\"" directive in the thrift file '
            'match the base_module specified in the TARGETS file?' %
            (py_flavor,))
        base_module = self.get_base_module(flavor=flavor, **kwargs)
        if base_module == None:
            base_module = base_path
            msg.append(
                '  base_module not specified, assumed to be "\\"%s\\""' %
                (base_path,))
        else:
            msg.append('  base_module is "\\"%s\\""' % (base_module,))

        expected_ns = [p for p in base_module.split('/') if p]
        expected_ns.append(thrift_base)
        expected_ns = '.'.join(expected_ns)
        msg.append(
            '  thrift file should contain "\\"namespace %s %s\\""' %
            (py_flavor, expected_ns,))

        cmd = 'if [ ! -f %s ]; then ' % (ttypes_path,)
        for line in msg:
            cmd += ' echo "%s" >&2;' % (line,)
        cmd += ' false; fi'

        return cmd

    def get_options(self, base_path, parsed_options):
        return self._get_options(base_path, parsed_options, self._flavor)

    def _get_options(self, base_path, parsed_options, flavor):
        options = {}

        # We always use new style for non-python3.
        if 'new_style' in parsed_options:
            fail('the "new_style" thrift python option is redundant')

        # Add flavor-specific option.
        if flavor == self.TWISTED:
            options['twisted'] = None
        elif flavor in (self.ASYNCIO, self.PYI_ASYNCIO):
            options['asyncio'] = None

        # Always use "new_style" classes.
        options['new_style'] = None

        options.update(parsed_options)

        return options

    def _add_ext(self, path, ext):
        if not path.endswith(ext):
            path += ext
        return path

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):
        return self._get_generated_sources(
            base_path,
            name,
            thrift_src,
            services,
            options,
            flavor = self._flavor,
            ext = self._ext,
            **kwargs)

    def _get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            flavor,
            ext,
            **kwargs):

        thrift_base = self.get_thrift_base(thrift_src)
        thrift_dir = self.get_thrift_dir(base_path, thrift_src, flavor, **kwargs)

        genfiles = []

        genfiles.append('constants' + ext)
        genfiles.append('ttypes' + ext)

        for service in services:
            # "<service>.py" and "<service>-remote" are generated for each
            # service
            genfiles.append(service + ext)
            if flavor == self.NORMAL:
                genfiles.append(service + '-remote')

        return {
            self._add_ext(paths.join(thrift_base, path), ext): paths.join('gen-py', thrift_dir, path)
            for path in genfiles
        }

    def get_pyi_dependency(self, name, flavor):
        if name.endswith('-asyncio'):
            name = name[:-len('-asyncio')]
        if name.endswith('-py'):
            name = name[:-len('-py')]
        if flavor == self.ASYNCIO:
            return name + '-pyi-asyncio'
        else:
            return name + '-pyi'

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            visibility,
            **kwargs):
        self._get_language_rule(
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            visibility,
            self._flavor,
            **kwargs)

    def _get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            visibility,
            flavor,
            **kwargs):

        srcs = thrift_common.merge_sources_map(sources_map)
        base_module = self.get_base_module(flavor, **kwargs)

        out_deps = []
        out_deps.extend(deps)

        # If this rule builds thrift files, automatically add a dependency
        # on the python thrift library.
        out_deps.append(target_utils.target_to_label(self.THRIFT_PY_LIB_RULE_NAME))

        # If thrift files are build with twisted support, add also
        # dependency on the thrift's twisted transport library.
        if flavor == self.TWISTED or 'twisted' in options:
            out_deps.append(
                target_utils.target_to_label(self.THRIFT_PY_TWISTED_LIB_RULE_NAME))

        # If thrift files are build with asyncio support, add also
        # dependency on the thrift's asyncio transport library.
        if flavor == self.ASYNCIO or 'asyncio' in options:
            out_deps.append(
                target_utils.target_to_label(self.THRIFT_PY_ASYNCIO_LIB_RULE_NAME))

        if flavor in (self.NORMAL, self.ASYNCIO):
            out_deps.append(':' + self.get_pyi_dependency(name, flavor))
            has_types = True
        else:
            has_types = False

        if get_typing_config_target():
            if has_types:
                gen_typing_config(
                    name,
                    base_module if base_module != None else base_path,
                    srcs.keys(),
                    out_deps,
                    typing=True,
                    visibility=visibility,
                )
            else:
                gen_typing_config(name)

        fb_native.python_library(
            name = name,
            visibility = visibility,
            srcs = srcs,
            base_module = base_module,
            deps = out_deps,
        )

class ThriftLibraryConverter(base.Converter):

    def __init__(self):
        super(ThriftLibraryConverter, self).__init__()

        # Setup the macro converters.
        converters = [
            cpp2_thrift_converter,
            d_thrift_converter,
            go_thrift_converter,
            haskell_deprecated_thrift_converter,
            haskell_hs2_thrift_converter,
            js_thrift_converter,
            ocaml_thrift_converter,
            rust_thrift_converter,
            thriftdoc_python_thrift_converter,
            python3_thrift_converter,
            LegacyPythonThriftConverter(
                flavor=LegacyPythonThriftConverter.NORMAL),
            LegacyPythonThriftConverter(
                flavor=LegacyPythonThriftConverter.ASYNCIO),
            LegacyPythonThriftConverter(
                flavor=LegacyPythonThriftConverter.TWISTED),
            LegacyPythonThriftConverter(
                flavor=LegacyPythonThriftConverter.PYI),
            LegacyPythonThriftConverter(
                flavor=LegacyPythonThriftConverter.PYI_ASYNCIO),
            java_deprecated_thrift_converter,
            java_deprecated_apache_thrift_converter,
            swift_thrift_converter,
        ]
        self._converters = {}
        self._name_to_lang = {}
        for converter in converters:
            self._converters[converter.get_lang()] = converter
            for name in converter.get_names():
                self._name_to_lang[name] = converter.get_lang()

    def get_fbconfig_rule_type(self):
        return 'thrift_library'

    def get_buck_rule_type(self):
        return 'thrift_library'

    def get_languages(self, names):
        """
        Convert the `languages` parameter to a normalized list of languages.
        """

        languages = set()

        if names == None:
            raise TypeError('thrift_library() requires languages argument')

        for name in names:
            lang = self._name_to_lang.get(name)
            if lang == None:
                raise TypeError(
                    'thrift_library() does not support language {!r}'
                    .format(name))
            if lang in languages:
                raise TypeError(
                    'thrift_library() given duplicate language {!r}'
                    .format(lang))
            languages.add(lang)

        return languages

    def parse_thrift_options(self, options):
        """
        Parse the option list or string into a dict.
        """

        parsed = collections.OrderedDict()

        if isinstance(options, basestring):
            options = options.split(',')

        for option in options:
            if '=' in option:
                option, val = option.rsplit('=', 1)
                parsed[option] = val
            else:
                parsed[option] = None

        return parsed

    def parse_thrift_args(self, args):
        """
        For some reason we accept `thrift_args` as either a list or
        space-separated string.
        """

        if isinstance(args, basestring):
            args = args.split()

        return args

    def get_thrift_options(self, options):
        if isinstance(options, basestring):
            options = options.split(',')
        return options

    def fixup_thrift_srcs(self, srcs):
        new_srcs = collections.OrderedDict()
        for name, services in sorted(srcs.items()):
            if services == None:
                services = []
            elif not isinstance(services, (tuple, list)):
                services = [services]
            new_srcs[name] = services
        return new_srcs

    def get_exported_include_tree(self, dep):
        """
        Generate the exported thrift source includes target use for the given
        thrift library target.
        """

        return dep + '-thrift-includes'

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
        converter = self._converters[lang]
        cmds.append(
            converter.get_compiler_command(
                compiler,
                compiler_args,
                self.get_exported_include_tree(':' + name),
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

        out = collections.OrderedDict()
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
        thrift_srcs = self.fixup_thrift_srcs(thrift_srcs)
        thrift_args = self.parse_thrift_args(thrift_args)
        languages = self.get_languages(languages)
        deps = [src_and_dep_helpers.convert_build_target(base_path, d) for d in deps]

        # Setup the exported include tree to dependents.
        includes = set()
        includes.update(thrift_srcs.keys())
        for lang in languages:
            converter = self._converters[lang]
            includes.update(converter.get_extra_includes(**kwargs))

        merge_tree(
            base_path,
            self.get_exported_include_tree(name),
            sorted(includes),
            map(self.get_exported_include_tree, deps),
            labels=["generated"],
            visibility=visibility)

        # py3 thrift requires cpp2
        if 'py3' in languages and 'cpp2' not in languages:
            languages.add('cpp2')

        # save cpp2_options for later use by 'py3'
        if 'cpp2' in languages:
            cpp2_options = (
                self.parse_thrift_options(
                    kwargs.get('thrift_cpp2_options', ())))

        # Types are generated for all legacy Python Thrift
        if 'py' in languages:
            languages.add('pyi')
            # Save the options for pyi to use
            py_options = (self.parse_thrift_options(
                kwargs.get('thrift_py_options', ())
            ))

        if 'py-asyncio' in languages:
            languages.add('pyi-asyncio')
            # Save the options for pyi to use
            py_asyncio_options = (self.parse_thrift_options(
                kwargs.get('thrift_py_asyncio_options', ())
            ))

        # Generate rules for all supported languages.
        for lang in languages:
            converter = self._converters[lang]
            compiler = converter.get_compiler()
            options = (
                self.parse_thrift_options(
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

            all_gen_srcs = collections.OrderedDict()
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
                    self.get_exported_include_tree(':' + name),
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
        langs.extend(self._name_to_lang.values())
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
            languages = set(languages) & set(supported_languages)

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
                thrift_srcs=self.fixup_thrift_srcs(kwargs.get('thrift_srcs', {})),
                base_module=kwargs.get('py_base_module'),
                include_sr=kwargs.get('py_remote_service_router', False),
                visibility=visibility)

        return []
