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
import hashlib

with allow_unsafe_import():  # noqa: magic
    import os


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
cpp = import_macro_lib('convert/cpp')
haskell = import_macro_lib('convert/haskell')
try:
    java = import_macro_lib('convert/java')
    use_internal_java_converters = True
except ImportError:
    use_internal_java_converters = False
js = import_macro_lib('convert/js')
cython = import_macro_lib('convert/cython')
ocaml = import_macro_lib('convert/ocaml')
python = import_macro_lib('convert/python')
rust = import_macro_lib('convert/rust')
Rule = import_macro_lib('rule').Rule
target = import_macro_lib('fbcode_target')
RootRuleTarget = target.RootRuleTarget
RuleTarget = target.RuleTarget
ThirdPartyRuleTarget = target.ThirdPartyRuleTarget


THRIFT_FLAGS = [
    '--allow-64bit-consts',
]


# The capitalize method from the string will also make the
# other characters in the word lower case.  This version only
# makes the first character upper case.
def capitalize(word):
    if len(word) > 0:
        return word[0].upper() + word[1:]
    return word


def camel(s):
    return ''.join(w[0].upper() + w[1:] for w in s.split('_') if w != '')


def format_options(options):
    """
    Format a thrift option dict into a compiler-ready string.
    """

    option_list = []

    for option, val in options.iteritems():
        if val is not None:
            option_list.append('{}={}'.format(option, val))
        else:
            option_list.append(option)

    return ','.join(option_list)


class ThriftLangConverter(base.Converter):
    """
    Base class for language-specific converters.  New languages should
    subclass this class.
    """

    def merge_sources_map(self, sources_map):
        sources = collections.OrderedDict()
        for srcs in sources_map.values():
            sources.update(srcs)
        return sources

    def get_thrift_dep_target(self, base_path, target):
        """
        Gets the translated target for a base_path and target. In fbcode, this
        will be a RootRuleTarget. Outside of fbcode, we have to make sure that
        the specified third-party repo is used
        """
        if self._context.config.get_current_repo_name() == 'fbcode':
            target = RootRuleTarget(base_path, target)
        else:
            repo = base_path.split('/')[0]
            target = ThirdPartyRuleTarget(repo, base_path, target)
        return self.get_dep_target(target)

    def get_compiler(self):
        """
        Return which thrift compiler to use.
        """

        return self._context.config.get_thrift_compiler()

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

        return []

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

        return None

    def get_additional_compiler(self):
        """
        Target of additional compiler that should be provided to the thrift1
        compiler (or None)
        """

        return None

    def get_compiler_args(
            self,
            flags,
            options,
            **kwargs):
        """
        Return args to pass into the compiler when generating sources.
        """

        args = []
        args.append('--gen')
        args.append(
            '{}:{}'.format(self.get_compiler_lang(), format_options(options)))
        args.extend(THRIFT_FLAGS)
        args.extend(flags)
        return args

    def get_compiler_command(
            self,
            compiler,
            compiler_args,
            includes):
        cmd = []
        cmd.append('$(exe {})'.format(compiler))
        cmd.extend(compiler_args)
        cmd.append('-I')
        cmd.append(
            '$(location {})'.format(includes))
        if self.read_bool('thrift', 'use_templates', True):
            cmd.append('--templates')
            cmd.append('$(location {})'.format(
                self._context.config.get_thrift_templates()))
        cmd.append('-o')
        cmd.append('"$OUT"')
        additional_compiler = self.get_additional_compiler()
        if additional_compiler:
            cmd.append('--python-compiler')
            cmd.append('$(query_outputs "{}")'.format(additional_compiler))
        cmd.append('"$SRCS"')
        return cmd

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

        return parsed_options

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources,
            deps,
            **kwargs):
        """
        Generate the language-specific library rule (and any extra necessary
        rules).
        """

        raise NotImplementedError()


class CppThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating C/C++ libraries from thrift sources.
    """

    STATIC_REFLECTION_SUFFIXES = [
        '', '_enum', '_union', '_struct', '_constant', '_service', '_types',
        '_all',
    ]

    TYPES_HEADER = 0
    TYPES_SOURCE = 1
    CLIENTS_HEADER = 2
    CLIENTS_SOURCE = 3
    SERVICES_HEADER = 4
    SERVICES_SOURCE = 5

    SUFFIXES = collections.OrderedDict([
        ('_constants.h', TYPES_HEADER),
        ('_constants.cpp', TYPES_SOURCE),
        ('_types.h', TYPES_HEADER),
        ('_types.tcc', TYPES_HEADER),
        ('_types.cpp', TYPES_SOURCE),
        ('_data.h', TYPES_HEADER),
        ('_data.cpp', TYPES_SOURCE),
        ('_layouts.h', TYPES_HEADER),
        ('_layouts.cpp', TYPES_SOURCE),
        ('_types_custom_protocol.h', TYPES_HEADER),
    ] + [
        ('_fatal%s.h' % suffix, TYPES_HEADER)
        for suffix in STATIC_REFLECTION_SUFFIXES
    ] + [
        ('_reflection.h', TYPES_HEADER),
        ('_reflection.cpp', TYPES_SOURCE),
        ('AsyncClient.h', CLIENTS_HEADER),
        ('_client.cpp', CLIENTS_SOURCE),
        ('_custom_protocol.h', SERVICES_HEADER),
        ('_processmap_binary.cpp', SERVICES_SOURCE),
        ('_processmap_compact.cpp', SERVICES_SOURCE),
        ('_gperf.tcc', SERVICES_HEADER),
        ('.tcc', SERVICES_HEADER),
        ('.h', SERVICES_HEADER),
        ('.cpp', SERVICES_SOURCE),
    ])

    def __init__(self, context, *args, **kwargs):
        is_cpp2 = kwargs.pop('is_cpp2', False)
        super(CppThriftConverter, self).__init__(context, *args, **kwargs)
        self._is_cpp2 = is_cpp2
        self._cpp_converter = cpp.CppConverter(context, 'cpp_library')

    def get_additional_compiler(self):
        return self._context.config.get_thrift2_compiler() if self._is_cpp2 else None

    def get_compiler(self):
        return self._context.config.get_thrift_compiler()

    def get_lang(self):
        return 'cpp2' if self._is_cpp2 else 'cpp'

    def get_compiler_lang(self):
        return 'mstch_cpp2' if self._is_cpp2 else 'cpp'

    def get_options(self, base_path, parsed_options):
        options = collections.OrderedDict()
        options['include_prefix'] = base_path
        options.update(parsed_options)
        if self._is_cpp2:
            options.pop('templates', None)
        return options

    def get_static_reflection(self, options):
        return self._is_cpp2 and ('reflection' in options or 'fatal' in options)

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):

        thrift_base = (
            os.path.splitext(
                os.path.basename(self.get_source_name(thrift_src)))[0])

        genfiles = []

        # The .tcc files will only be generated if the thrift C++ options
        # includes "templates".
        #
        # Returning .tcc files here when they aren't actually generated doesn't
        # cause build failures, but does cause make to rebuild files
        # unnecessarily on rebuilds.  It thinks the .tcc files are always
        # out-of-date, since they don't exist.
        is_bootstrap = 'bootstrap' in options
        gen_layouts = 'frozen2' in options
        gen_templates = self._is_cpp2 or 'templates' in options
        gen_perfhash = not self._is_cpp2 and 'perfhash' in options

        genfiles.append('%s_constants.h' % (thrift_base,))
        genfiles.append('%s_constants.cpp' % (thrift_base,))
        genfiles.append('%s_types.h' % (thrift_base,))
        genfiles.append('%s_types.cpp' % (thrift_base,))
        genfiles.append('%s_data.h' % (thrift_base,))
        genfiles.append('%s_data.cpp' % (thrift_base,))
        if self._is_cpp2:
            genfiles.append('%s_types_custom_protocol.h' % (thrift_base,))

        if gen_layouts:
            genfiles.append('%s_layouts.h' % (thrift_base,))
            genfiles.append('%s_layouts.cpp' % (thrift_base,))

        if self.get_static_reflection(options):
            for suffix in self.STATIC_REFLECTION_SUFFIXES:
                genfiles.append('%s_fatal%s.h' % (thrift_base, suffix))

        if gen_templates:
            genfiles.append('%s_types.tcc' % (thrift_base,))

        if not is_bootstrap and not self._is_cpp2:
            genfiles.append('%s_reflection.h' % (thrift_base,))
            genfiles.append('%s_reflection.cpp' % (thrift_base,))

        for service in services:
            genfiles.append('%s.h' % (service,))
            genfiles.append('%s.cpp' % (service,))
            if self._is_cpp2:
                genfiles.append('%s_client.cpp' % (service,))
                genfiles.append('%s_custom_protocol.h' % (service,))
                genfiles.append('%sAsyncClient.h' % (service,))
            if self._is_cpp2 and 'separate_processmap' in options:
                genfiles.append('%s_processmap_binary.cpp' % (service,))
                genfiles.append('%s_processmap_compact.cpp' % (service,))
            if gen_templates:
                genfiles.append('%s.tcc' % (service,))
            if gen_perfhash:
                genfiles.append('%s_gperf.tcc' % (service,))

        # Everything is in the 'gen-cpp' directory
        lang = self.get_lang()
        return collections.OrderedDict(
            [(p, p) for p in
                [os.path.join('gen-' + lang, path) for path in genfiles]])

    def _uses_mstch(self, options):
        non_mstch_flags = [
            'py_generator',
            'compatibility',
            'modulemap',
        ]
        return set(options.keys()).isdisjoint(non_mstch_flags)

    def is_header(self, src):
        _, ext = os.path.splitext(src)
        return ext in ('.h', '.tcc')

    def get_src_type(self, src):
        return next((
            type
            for suffix, type in self.SUFFIXES.items()
            if src.endswith(suffix)))

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            cpp_srcs=(),
            cpp2_srcs=(),
            cpp_headers=(),
            cpp2_headers=(),
            cpp_deps=(),
            cpp2_deps=(),
            cpp_external_deps=(),
            cpp2_external_deps=(),
            cpp_compiler_flags=(),
            cpp2_compiler_flags=(),
            **kwargs):
        """
        Generates a handful of rules:
            <name>-<lang>-types: A library that just has the 'types' h, tcc and
                          cpp files
            <name>-<lang>-clients: A library that just has the client and async
                                   client h and cpp files
            <name>-<lang>-services: A library that has h, tcc and cpp files
                                    needed to run a specific service
            <name>-<lang>: An uber rule for compatibility that just depends on
                           the three above rules
        This is done in order to trim down dependencies and compilation units
        when clients/services are not actually needed.
        """

        sources = self.merge_sources_map(sources_map)

        types_suffix = '-types'
        types_sources = self.convert_source_list(
            base_path, cpp2_srcs if self._is_cpp2 else cpp_srcs)
        types_headers = self.convert_source_list(
            base_path, cpp2_headers if self._is_cpp2 else cpp_headers)
        types_deps = [
            self.get_thrift_dep_target('folly', 'indestructible'),
            self.get_thrift_dep_target('folly', 'optional'),
        ]
        clients_and_services_suffix = '-clients_and_services'
        clients_suffix = '-clients'
        clients_sources = []
        clients_headers = []
        services_suffix = '-services'
        services_sources = []
        services_headers = []

        # If we're using mstch, we get a client that's separate entirely from
        # the service (XAsyncClient.h and X_client.cpp). If we /don't/ have
        # mstch, then we end up with a client that depends on the service
        # (X_client.cpp depends on X.h)
        # We also keep the client as a dependency of the service. The reason is
        # this:
        # Service.h includes ServiceAsyncClient.h. /this/ is because if you have
        # in non-mustache world, we put the client and service into one file.
        # We then include DependentService.h. If that dependency is generated
        # with mustache, we have no idea that the AsyncClient is in its own
        # file, rather than inside of the service's .h file, as it would be
        # if everything were generated with non-mustache. Once we're migrated,
        # the dependency of the service on the client rule can go away
        has_separate_client = self._uses_mstch(options)
        if has_separate_client:
            clients_deps = [
                self.get_thrift_dep_target('folly/futures', 'core'),
                self.get_thrift_dep_target('folly/io', 'iobuf'),
                ':%s%s' % (name, types_suffix),
            ]
            services_deps = [
                # TODO: Once everything is on mustache, remove this 'clients'
                # dependency
                ':%s%s' % (name, clients_suffix),
                ':%s%s' % (name, types_suffix),
            ]
        else:
            clients_deps = [':%s%s' % (name, types_suffix)]
            services_deps = clients_deps
            services_sources = clients_sources
            services_headers = clients_headers

        # Get sources/headers for the -types, -clients and -services rules
        for filename, file_target in sources.iteritems():
            source_type = self.get_src_type(filename)
            if source_type == self.TYPES_SOURCE:
                types_sources.append(file_target)
            elif source_type == self.TYPES_HEADER:
                types_headers.append(file_target)
            elif source_type == self.CLIENTS_SOURCE:
                clients_sources.append(file_target)
            elif source_type == self.CLIENTS_HEADER:
                clients_headers.append(file_target)
            elif source_type == self.SERVICES_SOURCE:
                services_sources.append(file_target)
            elif source_type == self.SERVICES_HEADER:
                services_headers.append(file_target)

        types_deps.extend((d + types_suffix for d in deps))
        clients_deps.extend((d + clients_suffix for d in deps))
        services_deps.extend((d + services_suffix for d in deps))

        # Add in cpp-specific deps and external_deps
        common_deps = []
        common_deps.extend(cpp2_deps if self._is_cpp2 else cpp_deps)
        common_external_deps = []
        common_external_deps.extend(
            cpp2_external_deps if self._is_cpp2 else cpp_external_deps)

        # Add required dependencies for Stream support
        if 'stream' in options:
            common_deps.append(
                self.get_thrift_dep_target('yarpl', 'yarpl'))
            clients_deps.append(
                self.get_thrift_dep_target(
                    'thrift/lib/cpp2/transport/core', 'thrift_client'))
            clients_deps.append(
                self.get_thrift_dep_target(
                    'thrift/lib/cpp2/transport/rsocket/client',
                    'stream_thrift_client'))
            services_deps.append(
                self.get_thrift_dep_target(
                    'thrift/lib/cpp2/transport/core',
                    'thrift_processor'))
        # The 'json' thrift option will generate code that includes
        # headers from deprecated/json.  So add a dependency on it here
        # so all external header paths will also be added.
        if 'json' in options:
            common_deps.append(
                self.get_thrift_dep_target('thrift/lib/cpp', 'json_deps'))
        if 'frozen' in options:
            common_deps.append(self.get_thrift_dep_target(
                'thrift/lib/cpp', 'frozen'))
        if 'frozen2' in options:
            common_deps.append(self.get_thrift_dep_target(
                'thrift/lib/cpp2/frozen', 'frozen'))

        # any c++ rule that generates thrift files must depend on the
        # thrift lib; add that dep now if it wasn't explicitly stated
        # already
        if self._is_cpp2:
            if 'bootstrap' not in options:
                types_deps.append(
                    self.get_thrift_dep_target('thrift/lib/cpp2', 'types_deps'))
                clients_deps.append(
                    self.get_thrift_dep_target('thrift/lib/cpp2', 'thrift_base'))
                services_deps.append(
                    self.get_thrift_dep_target('thrift/lib/cpp2', 'thrift_base'))
            # Make cpp2 depend on cpp for compatibility mode
            if 'compatibility' in options:
                common_deps.append(
                    self.get_thrift_dep_target(base_path, name[:-1]))
            if self.get_static_reflection(options):
                common_deps.append(
                    self.get_thrift_dep_target(
                        'thrift/lib/cpp2/fatal', 'reflection'))
        else:
            if 'bootstrap' not in options:
                common_deps.append(
                    self.get_thrift_dep_target('thrift/lib/cpp', 'thrift'))
            if 'cob_style' in options:
                common_deps.append(
                    self.get_thrift_dep_target('thrift/lib/cpp/async', 'async'))

        types_deps.extend(common_deps)
        services_deps.extend(common_deps)
        clients_deps.extend(common_deps)

        # Disable variable tracking for thrift generated C/C++ sources, as
        # it's pretty expensive and not necessarily useful (D2174972).
        common_compiler_flags = ['-fno-var-tracking']
        common_compiler_flags.extend(
            cpp2_compiler_flags if self._is_cpp2 else cpp_compiler_flags)

        clients_and_services_rules = []
        if not has_separate_client:
            # Munge everything into a backing rule so that we don't get
            # duplicate symbol errors if you statically link both -clients and
            # -servers
            rule_name = name + clients_and_services_suffix
            clients_and_services_rules = self._cpp_converter.convert(
                base_path,
                name=rule_name,
                srcs=clients_sources,
                headers=clients_headers,
                deps=clients_deps,
                external_deps=common_external_deps,
                compiler_flags=common_compiler_flags,
            )
            clients_sources = []
            clients_headers = []
            clients_deps = [':' + rule_name]
            services_sources = []
            services_headers = []
            services_deps = [':' + rule_name]

        # Create the types, services and clients rules
        # Delegate to the C/C++ library converting to add in things like
        # sanitizer and BUILD_MODE flags.
        types_rules = self._cpp_converter.convert(
            base_path,
            name=name + types_suffix,
            srcs=types_sources,
            headers=types_headers,
            deps=types_deps,
            external_deps=common_external_deps,
            compiler_flags=common_compiler_flags,
            # TODO(T23121628): Some rules have undefined symbols (e.g. uncomment
            # and build //thrift/lib/cpp2/test:exceptservice-cpp2-types).
            undefined_symbols=True,
        )
        clients_rules = self._cpp_converter.convert(
            base_path,
            name=name + clients_suffix,
            srcs=clients_sources,
            headers=clients_headers,
            deps=clients_deps,
            external_deps=common_external_deps,
            compiler_flags=common_compiler_flags,
            # TODO(T23121628): Some rules have undefined symbols (e.g. uncomment
            # and build //thrift/lib/cpp2/test:Presult-cpp2-clients).
            undefined_symbols=True,
        )
        services_rules = self._cpp_converter.convert(
            base_path,
            name + services_suffix,
            srcs=services_sources,
            headers=services_headers,
            deps=services_deps,
            external_deps=common_external_deps,
            compiler_flags=common_compiler_flags,
        )
        # Create a master rule that depends on -types, -services and -clients
        # for compatibility
        master_rules = self._cpp_converter.convert(
            base_path,
            name,
            srcs=[],
            headers=[],
            deps=[
                ':' + name + types_suffix,
                ':' + name + clients_suffix,
                ':' + name + services_suffix,
            ]
        )
        return (
            types_rules + clients_rules + services_rules +
            clients_and_services_rules + master_rules)


class DThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating D libraries from thrift sources.
    """

    def get_lang(self):
        return 'd'

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            d_thrift_namespaces=None,
            **kwargs):

        thrift_base = os.path.splitext(os.path.basename(thrift_src))[0]
        thrift_namespaces = d_thrift_namespaces or {}
        thrift_prefix = (
            thrift_namespaces.get(thrift_src, '').replace('.', os.sep))

        genfiles = []

        genfiles.append('%s_types.d' % thrift_base)
        genfiles.append('%s_constants.d' % thrift_base)

        for service in services:
            genfiles.append('%s.d' % service)

        return collections.OrderedDict(
            [(path, os.path.join('gen-d', path)) for path in
                [os.path.join(thrift_prefix, genfile) for genfile in genfiles]])

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):

        sources = self.merge_sources_map(sources_map)

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['srcs'] = sources

        out_deps = []
        out_deps.extend(deps)
        out_deps.append('//thrift/lib/d:thrift')
        attrs['deps'] = out_deps

        return [Rule('d_library', attrs)]


class GoThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating Go libraries from thrift sources.
    """
    def get_lang(self):
        return 'go'

    def go_package_name(
            self,
            go_thrift_namespaces,
            go_pkg_base_path,
            base_path,
            thrift_src):

        thrift_namespaces = go_thrift_namespaces or {}
        thrift_file = os.path.basename(thrift_src)
        try:
            namespace = thrift_namespaces[thrift_file]
            return namespace.replace('.', os.sep)
        except KeyError:
            if go_pkg_base_path is not None:
                base_path = go_pkg_base_path
            return os.path.join(base_path, os.path.splitext(thrift_file)[0])

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            go_thrift_namespaces=None,
            go_pkg_base_path=None,
            **kwargs):

        thrift_prefix = self.go_package_name(
            go_thrift_namespaces,
            go_pkg_base_path,
            base_path,
            thrift_src)

        genfiles = [
            'ttypes.go',
            'constants.go',
        ]

        for service in services:
            genfiles.append('{}.go'.format(service.lower()))

        return collections.OrderedDict(
            [(path, os.path.join('gen-go', path)) for path in
                [os.path.join(thrift_prefix, gf) for gf in genfiles]])

    def get_options(self, base_path, parsed_options):
        opts = collections.OrderedDict(
            thrift_import='thrift/lib/go/thrift',
        )
        opts.update(parsed_options)
        return opts

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            go_pkg_base_path=None,
            go_thrift_namespaces=None,
            go_thrift_src_inter_deps={},
            **kwargs):

        rules = []
        export_deps = set(deps)
        for thrift_src, sources in sources_map.iteritems():
            pkg = self.go_package_name(
                go_thrift_namespaces,
                go_pkg_base_path,
                base_path,
                thrift_src
            )
            thrift_noext = os.path.splitext(
                os.path.basename(thrift_src)
            )[0]

            rule_name = "{}-{}".format(name, os.path.basename(pkg))
            export_deps.add(":{}".format(rule_name))

            attrs = collections.OrderedDict()
            attrs['name'] = rule_name
            attrs['srcs'] = sources.values()
            attrs['package_name'] = pkg

            out_deps = []
            out_deps.extend(deps)
            out_deps.append('//thrift/lib/go/thrift:thrift')

            if thrift_noext in go_thrift_src_inter_deps:
                for local_dep in go_thrift_src_inter_deps[thrift_noext]:
                    local_dep_name = ":{}-{}".format(name, local_dep)
                    out_deps.append(local_dep_name)
                    export_deps.add(local_dep_name)

            attrs['deps'] = out_deps

            rules.extend([Rule('go_library', attrs)])

        # Generate a parent package with exported deps of the each thrift_src.
        # Since this package has no go source files and is never used directly
        # the name doesn't matter and it only needs to be unique.
        pkg_name = os.path.join(
            base_path,
            # generate unique package name to avoid pkg name clash
            hashlib.sha1("{}{}".format(name, rules)).hexdigest(),
        )

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['srcs'] = []
        attrs['package_name'] = pkg_name
        attrs['exported_deps'] = sorted(export_deps)

        rules.extend([Rule('go_library', attrs)])

        return rules


class HaskellThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating Haskell libraries from thrift sources.
    """

    THRIFT_HS_LIBS = [
        RootRuleTarget('thrift/lib/hs', 'thrift'),
        RootRuleTarget('thrift/lib/hs', 'types'),
        RootRuleTarget('thrift/lib/hs', 'protocol'),
        RootRuleTarget('thrift/lib/hs', 'transport'),
    ]

    THRIFT_HS_LIBS_DEPRECATED = [
        RootRuleTarget('thrift/lib/hs', 'hs'),
    ]

    THRIFT_HS2_LIBS = [
        RootRuleTarget('common/hs/thrift/lib', 'codegen-types-only'),
        RootRuleTarget('common/hs/thrift/lib', 'protocol'),
    ]

    THRIFT_HS2_SERVICE_LIBS = [
        RootRuleTarget('common/hs/thrift/lib', 'channel'),
        RootRuleTarget('common/hs/thrift/lib', 'codegen'),
        RootRuleTarget('common/hs/thrift/lib', 'processor'),
        RootRuleTarget('common/hs/thrift/lib', 'types'),
        RootRuleTarget('common/hs/thrift/lib/if', 'application-exception-hs2')
    ]

    THRIFT_DEPS = [
        ThirdPartyRuleTarget('stackage-lts', 'QuickCheck'),
        ThirdPartyRuleTarget('stackage-lts', 'vector'),
        ThirdPartyRuleTarget('stackage-lts', 'unordered-containers'),
        ThirdPartyRuleTarget('stackage-lts', 'text'),
        ThirdPartyRuleTarget('stackage-lts', 'hashable'),
        ThirdPartyRuleTarget('ghc', 'base'),
        ThirdPartyRuleTarget('ghc', 'bytestring'),
        ThirdPartyRuleTarget('ghc', 'containers'),
        ThirdPartyRuleTarget('ghc', 'deepseq'),
    ]

    THRIFT_HS2_DEPS = [
        ThirdPartyRuleTarget('ghc', 'base'),
        ThirdPartyRuleTarget('ghc', 'bytestring'),
        ThirdPartyRuleTarget('ghc', 'containers'),
        ThirdPartyRuleTarget('ghc', 'deepseq'),
        ThirdPartyRuleTarget('ghc', 'transformers'),
        ThirdPartyRuleTarget('stackage-lts', 'aeson'),
        ThirdPartyRuleTarget('stackage-lts', 'binary-parsers'),
        ThirdPartyRuleTarget('stackage-lts', 'data-default'),
        ThirdPartyRuleTarget('stackage-lts', 'hashable'),
        ThirdPartyRuleTarget('stackage-lts', 'STMonadTrans'),
        ThirdPartyRuleTarget('stackage-lts', 'text'),
        ThirdPartyRuleTarget('stackage-lts', 'unordered-containers'),
        ThirdPartyRuleTarget('stackage-lts', 'vector'),
    ]

    def __init__(self, context, *args, **kwargs):
        is_hs2 = kwargs.pop('is_hs2', False)
        super(HaskellThriftConverter, self).__init__(context, *args, **kwargs)
        self._is_hs2 = is_hs2
        self._hs_converter = (
            haskell.HaskellConverter(context, 'haskell_library'))

    def get_compiler(self):
        if self._is_hs2:
            return self._context.config.get_thrift_hs2_compiler()
        else:
            return self._context.config.get_thrift_compiler()

    def get_lang(self):
        return 'hs2' if self._is_hs2 else 'hs'

    def get_extra_includes(self, hs_includes=(), **kwargs):
        return hs_includes

    def get_compiler_args(
            self,
            flags,
            options,
            hs_required_symbols=None,
            **kwargs):
        """
        Return compiler args when compiling for haskell languages.
        """

        # If this isn't `hs2` fall back to getting the regular copmiler args.
        if self.get_lang() != 'hs2':
            return super(HaskellThriftConverter, self).get_compiler_args(
                flags,
                options)

        args = ["--hs"]

        # Format the options and pass them into the hs2 compiler.
        for option, val in options.iteritems():
            flag = '--' + option
            if val is not None:
                flag += '=' + val
            args.append(flag)

        # Include rule-specific flags.
        args.extend(flags)

        # Add in the require symbols parameter.
        if hs_required_symbols is not None:
            args.append('--required-symbols')
            args.append(hs_required_symbols)

        return args

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            hs_namespace=None,
            **kwargs):

        thrift_base = os.path.splitext(os.path.basename(thrift_src))[0]
        thrift_base = capitalize(thrift_base)
        namespace = hs_namespace or ''
        lang = self.get_lang()

        genfiles = []

        if lang == 'hs':
            genfiles.append('%s_Consts.hs' % thrift_base)
            genfiles.append('%s_Types.hs' % thrift_base)
            for service in services:
                service = capitalize(service)
                genfiles.append('%s.hs' % service)
                genfiles.append('%s_Client.hs' % service)
                genfiles.append('%s_Iface.hs' % service)
                genfiles.append('%s_Fuzzer.hs' % service)
            namespace = namespace.replace('.', '/')

        elif lang == 'hs2':
            thrift_base = camel(thrift_base)
            namespace = os.sep.join(map(camel, namespace.split('.')))
            genfiles.append('%s/Types.hs' % thrift_base)
            for service in services:
                genfiles.append('%s/%s/Client.hs' % (thrift_base, service))
                genfiles.append('%s/%s/Service.hs' % (thrift_base, service))

        return collections.OrderedDict(
            [(path, os.path.join('gen-' + lang, path)) for path in
                [os.path.join(namespace, genfile) for genfile in genfiles]])

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            hs_packages=(),
            hs2_deps=[],
            **kwargs):

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['srcs'] = self.merge_sources_map(sources_map)

        dependencies = []
        if not self._is_hs2:
            dependencies.extend(self.THRIFT_DEPS)
            if 'new_deps' in options:
                dependencies.extend(self.THRIFT_HS_LIBS)
            else:
                dependencies.extend(self.THRIFT_HS_LIBS_DEPRECATED)
        else:
            for services in thrift_srcs.itervalues():
                if services:
                    dependencies.extend(self.THRIFT_HS2_SERVICE_LIBS)
                    break
            dependencies.extend(self.THRIFT_HS2_DEPS)
            dependencies.extend(self.THRIFT_HS2_LIBS)
            for pkg in hs_packages or []:
                dependencies.append(self._hs_converter.get_dep_for_package(pkg))
            for dep in hs2_deps:
                dependencies.append(target.parse_target(dep, base_path))
        for dep in deps:
            dependencies.append(target.parse_target(dep, base_path))
        attrs['deps'], attrs['platform_deps'] = (
            self.format_all_deps(dependencies))
        if self.read_hs_profile():
            attrs['enable_profiling'] = True

        return [Rule('haskell_library', attrs)]


class JavaDeprecatedThriftBaseConverter(ThriftLangConverter):
    """
    Specializer to support generating Java libraries from thrift sources
    using plain fbthrift or Apache Thrift.
    """

    def __init__(self, context, *args, **kwargs):
        super(JavaDeprecatedThriftBaseConverter, self).__init__(
            context, *args, **kwargs)
        self._java_library_converter = java.JavaLibraryConverter(context)

    def get_compiler_lang(self):
        return 'java'

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):

        # We want *all* the generated sources, so top-level directory.
        return collections.OrderedDict([('', 'gen-java')])

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            java_thrift_maven_coords=None,
            **kwargs):

        rules = []
        out_srcs = []

        # Pack all generated source directories into a source zip, which we'll
        # feed into the Java library rule.
        if sources_map:
            src_zip_name = name + '.src.zip'
            attrs = collections.OrderedDict()
            attrs['name'] = src_zip_name
            attrs['srcs'] = (
                [source for sources in sources_map.itervalues()
                    for source in sources.itervalues()])
            attrs['out'] = src_zip_name
            rules.append(Rule('zip_file', attrs))
            out_srcs.append(':' + src_zip_name)

        # Wrap the source zip in a java library rule, with an implicit dep on
        # the thrift library.
        out_deps = []
        out_deps.extend(deps)
        out_deps.extend(self._get_runtime_dependencies())
        rules.extend(self._java_library_converter.convert(
            base_path,
            name=name,
            srcs=out_srcs,
            exported_deps=out_deps,
            maven_coords=java_thrift_maven_coords))

        return rules


class JavaDeprecatedThriftConverter(JavaDeprecatedThriftBaseConverter):
    """
    Specializer to support generating Java libraries from thrift sources
    using fbthrift.
    """

    def __init__(self, context, *args, **kwargs):
        super(JavaDeprecatedThriftConverter, self).__init__(
            context, *args, **kwargs)

    def get_compiler(self):
        return self.read_string(
            'thrift', 'compiler',
            super(JavaDeprecatedThriftConverter, self).get_compiler())

    def get_lang(self):
        return 'javadeprecated'

    def _get_runtime_dependencies(self):
        return [
            '//thrift/lib/java:thrift',
            '//third-party-java/org.slf4j:slf4j-api',
        ]


class JavaDeprecatedApacheThriftConverter(JavaDeprecatedThriftBaseConverter):
    """
    Specializer to support generating Java libraries from thrift sources
    using the Apache Thrift compiler.
    """

    def __init__(self, context, *args, **kwargs):
        super(JavaDeprecatedApacheThriftConverter, self).__init__(
            context, *args, **kwargs)

    def get_lang(self):
        return 'javadeprecated-apache'

    def get_compiler(self):
        return self._context.config.get_thrift_deprecated_apache_compiler()

    def get_compiler_command(
            self,
            compiler,
            compiler_args,
            includes):
        cmd = []
        cmd.append('$(exe {})'.format(compiler))
        cmd.extend(compiler_args)
        cmd.append('-I')
        cmd.append(
            '$(location {})'.format(includes))
        cmd.append('-o')
        cmd.append('"$OUT"')
        cmd.append('"$SRCS"')
        return cmd

    def _get_runtime_dependencies(self):
        return [
            '//third-party-java/org.apache.thrift:libthrift',
            '//third-party-java/org.slf4j:slf4j-api',
        ]


class JsThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating D libraries from thrift sources.
    """

    def __init__(self, context, *args, **kwargs):
        super(JsThriftConverter, self).__init__(context, *args, **kwargs)
        self._js_converter = js.JsConverter(context, 'js_npm_module')

    def get_lang(self):
        return 'js'

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):

        thrift_base = os.path.splitext(os.path.basename(thrift_src))[0]

        genfiles = []
        genfiles.append('%s_types.js' % thrift_base)
        for service in services:
            genfiles.append('%s.js' % service)

        out_dir = 'gen-nodejs' if 'node' in options else 'gen-js'
        gen_srcs = collections.OrderedDict()
        for path in genfiles:
            dst = os.path.join('node_modules', thrift_base, path)
            src = os.path.join(out_dir, path)
            gen_srcs[dst] = src

        return gen_srcs

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):

        sources = self.merge_sources_map(sources_map)

        cmds = []

        for dep in deps:
            cmds.append('rsync -a $(location {})/ "$OUT"'.format(dep))

        for dst, raw_src in sources.iteritems():
            src = self.get_source_name(raw_src)
            dst = os.path.join('"$OUT"', dst)
            cmds.append('mkdir -p {}'.format(os.path.dirname(dst)))
            cmds.append('cp {} {}'.format(os.path.basename(src), dst))

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['out'] = os.curdir
        attrs['srcs'] = sources.values()
        attrs['cmd'] = ' && '.join(cmds)
        return [Rule('genrule', attrs)]


class JavaSwiftConverter(ThriftLangConverter):
    """
    Specializer to support generating Java Swift libraries from thrift sources.
    """
    tweaks = set(['EXTEND_RUNTIME_EXCEPTION'])

    def __init__(self, context, *args, **kwargs):
        super(JavaSwiftConverter, self).__init__(context, *args, **kwargs)
        self._java_library_converter = java.JavaLibraryConverter(context)

    def get_lang(self):
        return 'java-swift'

    def get_compiler(self):
        return self._context.config.get_thrift_swift_compiler()

    def get_compiler_args(
            self,
            flags,
            options,
            **kwargs):
        """
        Return args to pass into the compiler when generating sources.
        """
        args = [
            '-tweak', 'ADD_CLOSEABLE_INTERFACE',
        ]
        add_thrift_exception = True
        for option in options:
            if option == 'T22418930_DO_NOT_USE_generate_beans':
                args.append('-generate_beans')
            elif option == 'T22418930_DO_NOT_USE_unadd_thrift_exception':
                add_thrift_exception = False
            elif option in JavaSwiftConverter.tweaks:
                args.append('-tweak')
                args.append(option)
            else:
                raise ValueError(
                    'the "{0}" java-swift option is invalid'.format(option))
        if add_thrift_exception:
            args.extend(['-tweak', 'ADD_THRIFT_EXCEPTION'])
        return args

    def get_compiler_command(
            self,
            compiler,
            compiler_args,
            includes):
        cmd = []
        cmd.append('$(exe {})'.format(compiler))
        cmd.append('-include_paths')
        cmd.append(
            '$(location {})'.format(includes))
        cmd.extend(compiler_args)
        cmd.append('-out')
        # We manually set gen-swift here for the purposes of following
        # the convention in the fbthrift generator
        cmd.append('"$OUT"{}'.format('/gen-swift'))
        cmd.append('"$SRCS"')
        return cmd

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_srcs,
            services,
            options,
            **kwargs):
        # we want all the sources under gen-swift
        return collections.OrderedDict([('', 'gen-swift')])

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            java_swift_maven_coords=None,
            **kwargs):
        rules = []
        out_srcs = []

        # Pack all generated source directories into a source zip, which we'll
        # feed into the Java library rule.
        if sources_map:
            src_zip_name = name + '.src.zip'
            attrs = collections.OrderedDict()
            attrs['name'] = src_zip_name
            attrs['srcs'] = (
                [source for sources in sources_map.values()
                    for source in sources.values()])
            attrs['out'] = src_zip_name
            rules.append(Rule('zip_file', attrs))
            out_srcs.append(':' + src_zip_name)

        out_deps = []
        out_deps.extend(deps)
        out_deps.append('//third-party-java/com.google.guava:guava')
        out_deps.append('//third-party-java/org.apache.thrift:libthrift')
        out_deps.append(
            '//third-party-java/com.facebook.swift:swift-annotations')

        maven_publisher_enabled = False
        if java_swift_maven_coords is not None:
            maven_publisher_enabled = True
            expected_coords_prefix = "com.facebook.thrift:"
            if not java_swift_maven_coords.startswith(expected_coords_prefix):
                raise ValueError(
                    "java_swift_maven_coords must start with '%s'"
                    % expected_coords_prefix)
            expected_options = set(['EXTEND_RUNTIME_EXCEPTION'])
            if set(options) != expected_options:
                raise ValueError(
                    "When java_swift_maven_coords is specified, you must set"
                    " thrift_java_swift_options = %s" % expected_options)

        rules.extend(self._java_library_converter.convert(
            base_path,
            name=name,
            srcs=out_srcs,
            exported_deps=out_deps,
            maven_coords=java_swift_maven_coords,
            maven_publisher_enabled=maven_publisher_enabled))

        return rules


class LegacyPythonThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating Python libraries from thrift sources.
    """

    NORMAL = 'normal'
    TWISTED = 'twisted'
    ASYNCIO = 'asyncio'
    PYI = 'pyi'
    PYI_ASYNCIO = 'pyi-asyncio'

    THRIFT_PY_LIB_RULE_NAME = RootRuleTarget('thrift/lib/py', 'py')
    THRIFT_PY_TWISTED_LIB_RULE_NAME = RootRuleTarget('thrift/lib/py', 'twisted')
    THRIFT_PY_ASYNCIO_LIB_RULE_NAME = RootRuleTarget('thrift/lib/py', 'asyncio')

    def __init__(self, context, *args, **kwargs):
        flavor = kwargs.pop('flavor', self.NORMAL)
        super(LegacyPythonThriftConverter, self).__init__(
            context,
            *args,
            **kwargs
        )
        self._flavor = flavor
        self._ext = '.py' if flavor not in (self.PYI, self.PYI_ASYNCIO) else '.pyi'

    def get_name(self, prefix, sep, base_module=False):
        flavor = self._flavor
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
        return frozenset([
            self.get_name('py', '-'),
            self.get_name('python', '-')])

    def get_lang(self, prefix='py'):
        return self.get_name('py', '-')

    def get_compiler_lang(self):
        if self._flavor in (self.PYI, self.PYI_ASYNCIO):
            return 'mstch_pyi'
        return 'py'

    def get_thrift_base(self, thrift_src):
        return os.path.splitext(os.path.basename(thrift_src))[0]

    def get_base_module(self, **kwargs):
        """
        Get the user-specified base-module set in via the parameter in the
        `thrift_library()`.
        """

        base_module = kwargs.get(
            self.get_name('py', '_', base_module=True) + '_base_module')

        # If no asyncio/twisted specific base module parameter is present,
        # fallback to using the general `py_base_module` parameter.
        if base_module is None:
            base_module = kwargs.get('py_base_module')

        # If nothing is set, just return `None`.
        if base_module is None:
            return None

        # Otherwise, since we accept pathy base modules, normalize it to look
        # like a proper module.
        return os.sep.join(base_module.split('.'))

    def get_thrift_dir(self, base_path, thrift_src, **kwargs):
        thrift_base = self.get_thrift_base(thrift_src)
        base_module = self.get_base_module(**kwargs)
        if base_module is None:
            base_module = base_path
        return os.path.join(base_module, thrift_base)

    def get_postprocess_command(
            self,
            base_path,
            thrift_src,
            out_dir,
            **kwargs):

        # The location of the generated thrift files depends on the value of
        # the "namespace py" directive in the .thrift file, and we
        # unfortunately don't know what this value is.  After compilation, make
        # sure the ttypes.py file exists in the location we expect.  If not,
        # there is probably a mismatch between the base_module parameter in the
        # TARGETS file and the "namespace py" directive in the .thrift file.
        thrift_base = self.get_thrift_base(thrift_src)
        thrift_dir = self.get_thrift_dir(base_path, thrift_src, **kwargs)

        output_dir = os.path.join(out_dir, 'gen-py', thrift_dir)
        ttypes_path = os.path.join(output_dir, 'ttypes' + self._ext)

        msg = [
            'Compiling %s did not generate source in %s'
            % (os.path.join(base_path, thrift_src), ttypes_path)
        ]
        if self._flavor == self.ASYNCIO or self._flavor == self.PYI_ASYNCIO:
            py_flavor = 'py.asyncio'
        elif self._flavor == self.TWISTED:
            py_flavor = 'py.twisted'
        else:
            py_flavor = 'py'
        msg.append(
            'Does the "\\"namespace %s\\"" directive in the thrift file '
            'match the base_module specified in the TARGETS file?' %
            (py_flavor,))
        base_module = self.get_base_module(**kwargs)
        if base_module is None:
            base_module = base_path
            msg.append(
                '  base_module not specified, assumed to be "\\"%s\\""' %
                (base_path,))
        else:
            msg.append('  base_module is "\\"%s\\""' % (base_module,))

        expected_ns = [p for p in base_module.split(os.sep) if p]
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
        options = collections.OrderedDict()

        # We always use new style for non-python3.
        if 'new_style' in parsed_options:
            raise ValueError(
                'the "new_style" thrift python option is redundant')

        # Add flavor-specific option.
        if self._flavor == self.TWISTED:
            options['twisted'] = None
        elif self._flavor in (self.ASYNCIO, self.PYI_ASYNCIO):
            options['asyncio'] = None

        # Always use "new_style" classes.
        options['new_style'] = None

        options.update(parsed_options)

        return options

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):

        thrift_base = self.get_thrift_base(thrift_src)
        thrift_dir = self.get_thrift_dir(base_path, thrift_src, **kwargs)

        genfiles = []

        genfiles.append('constants' + self._ext)
        genfiles.append('ttypes' + self._ext)

        for service in services:
            # "<service>.py" and "<service>-remote" are generated for each
            # service
            genfiles.append(service + self._ext)
            if self._flavor == self.NORMAL:
                genfiles.append(service + '-remote')

        def add_ext(path, ext):
            if not path.endswith(ext):
                path += ext
            return path

        return collections.OrderedDict(
            [(add_ext(os.path.join(thrift_base, path), self._ext),
              os.path.join('gen-py', thrift_dir, path)) for path in genfiles])

    def get_pyi_dependency(self, name):
        if name.endswith('-asyncio'):
            name = name[:-len('-asyncio')]
        if name.endswith('-py'):
            name = name[:-len('-py')]
        if self._flavor == self.ASYNCIO:
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
            **kwargs):

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['srcs'] = self.merge_sources_map(sources_map)
        attrs['base_module'] = self.get_base_module(**kwargs)

        out_deps = []
        out_deps.extend(deps)

        # If this rule builds thrift files, automatically add a dependency
        # on the python thrift library.
        out_deps.append(self.get_dep_target(self.THRIFT_PY_LIB_RULE_NAME))

        # If thrift files are build with twisted support, add also
        # dependency on the thrift's twisted transport library.
        if self._flavor == self.TWISTED or 'twisted' in options:
            out_deps.append(
                self.get_dep_target(self.THRIFT_PY_TWISTED_LIB_RULE_NAME))

        # If thrift files are build with asyncio support, add also
        # dependency on the thrift's asyncio transport library.
        if self._flavor == self.ASYNCIO or 'asyncio' in options:
            out_deps.append(
                self.get_dep_target(self.THRIFT_PY_ASYNCIO_LIB_RULE_NAME))

        if self._flavor in (self.NORMAL, self.ASYNCIO):
            out_deps.append(':' + self.get_pyi_dependency(name))

        attrs['deps'] = out_deps
        if self.typing_config_target:
            base_module = attrs['base_module']
            yield self.gen_typing_config(
                attrs['name'],
                base_module if base_module is not None else base_path,
                attrs['srcs'],
                out_deps,
                typing=True
            )
        yield Rule('python_library', attrs)


class OCamlThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating OCaml libraries from thrift sources.
    """

    THRIFT_OCAML_LIBS = [
        RootRuleTarget('common/ocaml/thrift', 'thrift'),
    ]

    THRIFT_OCAML_DEPS = [
        RootRuleTarget('hphp/hack/src/third-party/core', 'core'),
    ]

    def __init__(self, context, *args, **kwargs):
        super(OCamlThriftConverter, self).__init__(context, *args, **kwargs)
        self._ocaml_converter = (
            ocaml.OCamlConverter(context, 'ocaml_library'))

    def get_compiler(self):
        return self._context.config.get_thrift_ocaml_compiler()

    def get_lang(self):
        return 'ocaml2'

    def get_extra_includes(self, **kwargs):
        return []

    def get_compiler_args(
            self,
            flags,
            options,
            **kwargs):
        """
        Return compiler args when compiling for ocaml.
        """

        args = []

        # The OCaml compiler relies on the HS2 compiler to parse .thrift sources to JSON
        args.append('-c')
        args.append('$(exe {})'.format(self._context.config.get_thrift_hs2_compiler()))

        # Format the options and pass them into the ocaml compiler.
        for option, val in options.iteritems():
            flag = '--' + option
            if val is not None:
                flag += '=' + val
            args.append(flag)

        # Include rule-specific flags.
        args.extend(flags)

        return args

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):

        thrift_base = os.path.splitext(os.path.basename(thrift_src))[0]
        thrift_base = capitalize(thrift_base)

        genfiles = []

        genfiles.append('%s_consts.ml' % thrift_base)
        genfiles.append('%s_types.ml' % thrift_base)
        for service in services:
            service = capitalize(service)
            genfiles.append('%s.ml' % service)

        return collections.OrderedDict(
            [(path, path) for path in genfiles])

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['srcs'] = self.merge_sources_map(sources_map).values()

        dependencies = []
        dependencies.extend(self.THRIFT_OCAML_DEPS)
        dependencies.extend(self.THRIFT_OCAML_LIBS)
        for dep in deps:
            dependencies.append(target.parse_target(dep, base_path))
        attrs['deps'] = (self.format_all_deps(dependencies))[0]

        return [Rule('ocaml_library', attrs)]


class Python3ThriftConverter(ThriftLangConverter):
    CYTHON_TYPES_GENFILES = (
        'types.pxd',
        'types.pyx',
        'types.pyi',
    )

    CYTHON_RPC_GENFILES = (
        'services.pxd',
        'services.pyx',
        'services.pyi',
        'services_wrapper.pxd',
        'clients.pyx',
        'clients.pxd',
        'clients.pyi',
        'clients_wrapper.pxd'
    )

    CXX_RPC_GENFILES = (
        'services_wrapper.cpp',
        'services_wrapper.h',
        'clients_wrapper.cpp',
        'clients_wrapper.h',
    )

    types_suffix = '-types'
    services_suffix = '-services'
    clients_suffix = '-clients'

    def __init__(self, context, *args, **kwargs):
        super(Python3ThriftConverter, self).__init__(context, *args, **kwargs)
        self.cython_library = cython.Converter(context)

    def get_lang(self):
        return 'py3'

    def get_compiler_lang(self):
        return 'mstch_py3'

    def get_options(self, base_path, parsed_options):
        options = collections.OrderedDict()
        options['include_prefix'] = base_path
        options.update(parsed_options)
        return options

    def get_postprocess_command(
            self,
            base_path,
            thrift_src,
            out_dir,
            py3_namespace='',
            **kwargs):

        # The location of the generated thrift files depends on the value of
        # the "namespace py3" directive in the .thrift file, and we
        # unfortunately don't know what this value is.  After compilation, make
        # sure the types.pyx file exists in the location we expect.  If not,
        # there is probably a mismatch between the py3_namespace parameter in the
        # TARGETS file and the "namespace py3" directive in the .thrift file.
        thrift_name = self.thrift_name(thrift_src)
        package = os.path.join(py3_namespace, thrift_name).replace('.', '/')
        output_dir = os.path.join(out_dir, 'gen-py3', package)
        types_path = os.path.join(output_dir, 'types.pyx')

        msg = [
            'Compiling %s did not generate source in %s'
            % (os.path.join(base_path, thrift_src), types_path)
        ]
        msg.append(
            "Does the 'namespace py3' directive in the thrift file "
            'match the py3_namespace specified in the TARGETS file?')
        msg.append('  py3_namespace is {!r}'.format(py3_namespace))
        if py3_namespace:
            msg.append(
                "  thrift file should contain 'namespace py3 {}'".format(py3_namespace)
            )
        else:
            msg.append(
                "  thrift file should not contain any 'namespace py3' directive"
            )

        cmd = 'if [ ! -f %s ]; then ' % (types_path,)
        for line in msg:
            cmd += ' echo "%s" >&2;' % (line,)
        cmd += ' false; fi'

        return cmd

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            py3_namespace='',
            **kwargs):
        """
        Return a dict of all generated thrift sources, mapping the logical
        language-specific name to the path of the generated source relative
        to the thrift compiler output directory.

        cpp files and cython files have different paths because of
        their different compilation behaviors
        """
        thrift_name = self.thrift_name(thrift_src)
        package = os.path.join(py3_namespace, thrift_name).replace('.', '/')

        # If there are services defined then there will be services/clients files
        # and cpp files.
        if services:
            cython_genfiles = self.CYTHON_TYPES_GENFILES + self.CYTHON_RPC_GENFILES
            cpp_genfiles = self.CXX_RPC_GENFILES
        else:
            cython_genfiles = self.CYTHON_TYPES_GENFILES
            cpp_genfiles = ()

        cython_paths = (
            os.path.join(package, genfile)
            for genfile in cython_genfiles
        )

        cpp_paths = (
            os.path.join(thrift_name, genfile)
            for genfile in cpp_genfiles
        )

        return collections.OrderedDict((
            (path, os.path.join('gen-py3', path))
            for path in itertools.chain(cython_paths, cpp_paths)
        ))

    def thrift_name(self, thrift_src):
        return os.path.splitext(os.path.basename(thrift_src))[0]

    def get_cpp2_dep(self, dep):
        if dep.endswith('-py3'):
            dep = dep[:-len('-py3')]

        return dep + '-cpp2'

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources,
            deps,
            py3_namespace='',
            **kwargs):
        """
        Generate the language-specific library rule (and any extra necessary
        rules).
        """

        def generated(src, thrift_src):
            thrift_name = self.thrift_name(thrift_src)
            thrift_package = os.path.join(thrift_name, src)
            if src in self.CXX_RPC_GENFILES:
                full_src = thrift_package
                dst = os.path.join('gen-py3', full_src)
            else:
                full_src = os.path.join(
                    py3_namespace.replace('.', '/'), thrift_package
                )
                dst = thrift_package
            return sources[thrift_src][full_src], dst

        for gen_func in (self.gen_rule_thrift_types,
                         self.gen_rule_thrift_services,
                         self.gen_rule_thrift_clients):
            for rule in gen_func(
                name, base_path, sources, thrift_srcs,
                py3_namespace, deps, generated
            ):
                yield rule

    def gen_rule_thrift_types(
        self, name, base_path, sources, thrift_srcs, namespace, fdeps, generated,
    ):
        """Generates rules for Thrift types."""

        for rule in self.cython_library.convert(
            name=name + self.types_suffix,
            base_path=base_path,
            package=namespace,
            srcs=collections.OrderedDict((generated('types.pyx', src)
                                          for src in thrift_srcs)),
            headers=collections.OrderedDict((generated('types.pxd', src)
                                             for src in thrift_srcs)),
            types=collections.OrderedDict((generated('types.pyi', src)
                                          for src in thrift_srcs)),
            cpp_deps=[':' + self.get_cpp2_dep(name)] + [
                self.get_cpp2_dep(d) for d in fdeps
            ],
            deps=[
                self.get_thrift_dep_target('thrift/lib/py3', 'exceptions'),
                self.get_thrift_dep_target('thrift/lib/py3', 'std_libcpp'),
                self.get_thrift_dep_target('thrift/lib/py3', 'types'),
            ] + [d + self.types_suffix for d in fdeps],
            cpp_compiler_flags=['-fno-strict-aliasing'],
        ):
            yield rule

    def gen_rule_thrift_services(
        self, name, base_path, sources, thrift_srcs, namespace, fdeps, generated,
    ):
        """Generate rules for Thrift Services"""
        # Services and support
        def services_srcs():
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                yield generated('services.pyx', src)
                yield generated('services_wrapper.cpp', src)

        def services_headers():
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                yield generated('services.pxd', src)
                yield generated('services_wrapper.pxd', src)
                yield generated('services_wrapper.h', src)

        def services_typing():
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                yield generated('services.pyi', src)

        def cython_api(module, thrift_srcs):
            """Build out a cython_api dict, to place the _api.h files inside
            the gen-py3/ root so the c++ code can find it
            """
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                thrift_name = self.thrift_name(src)
                module_path = os.path.join(thrift_name, module)
                dst = os.path.join('gen-py3', module_path)
                yield module_path, dst

        for rule in self.cython_library.convert(
            name=name + self.services_suffix,
            base_path=base_path,
            package=namespace,
            srcs=collections.OrderedDict(services_srcs()),
            headers=collections.OrderedDict(services_headers()),
            types=collections.OrderedDict(services_typing()),
            cpp_deps=[
                ':' + self.get_cpp2_dep(name),
            ],
            deps=[
                ':' + name + self.types_suffix,
                self.get_thrift_dep_target('thrift/lib/py3', 'server'),
            ] + [d + self.services_suffix for d in fdeps],
            cpp_compiler_flags=['-fno-strict-aliasing'],
            api=collections.OrderedDict(
                cython_api('services', thrift_srcs)),
        ):
            yield rule

    def gen_rule_thrift_clients(
        self, name, base_path, sources, thrift_srcs, namespace, fdeps, generated,
    ):
        # Clients and support
        def clients_srcs():
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                yield generated('clients.pyx', src)
                yield generated('clients_wrapper.cpp', src)

        def clients_headers():
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                yield generated('clients.pxd', src)
                yield generated('clients_wrapper.pxd', src)
                yield generated('clients_wrapper.h', src)

        def clients_typing():
            for src, services in thrift_srcs.items():
                if not services:
                    continue
                yield generated('clients.pyi', src)

        for rule in self.cython_library.convert(
            name=name + self.clients_suffix,
            base_path=base_path,
            package=namespace,
            srcs=collections.OrderedDict(clients_srcs()),
            headers=collections.OrderedDict(clients_headers()),
            types=collections.OrderedDict(clients_typing()),
            cpp_deps=[
                ':' + self.get_cpp2_dep(name),
            ],
            deps=[
                ':' + name + self.types_suffix,
                self.get_thrift_dep_target('thrift/lib/py3', 'client'),
            ] + [d + self.clients_suffix for d in fdeps],
            cpp_compiler_flags=['-fno-strict-aliasing'],
        ):
            yield rule


class ThriftdocPythonThriftConverter(ThriftLangConverter):
    '''
    Given a `thrift_library`:
     - Runs the `json_experimental` Thrift generator for each of its
       `.thrift` files.
     - Converts each of the resulting `.json` into a PAR-importable
       `thriftdoc_ast.py` file, while parsing the Thriftdoc validation DSL.
     - Packaged the ASTs into a `python_library` that can be used for Thrift
       struct validation.

    Import this to get started with Thriftdoc validation:
        tupperware.thriftdoc.validator.validate_thriftdoc
    Documentation is at:
        https://our.intern.facebook.com/intern/wiki/ThriftdocGuide
    '''

    AST_FILE = 'thriftdoc_ast.py'

    def __init__(self, context, *args, **kwargs):
        super(ThriftdocPythonThriftConverter, self).__init__(
            context, *args, **kwargs
        )

    def get_lang(self):
        return 'thriftdoc-py'

    def get_compiler_lang(self):
        return 'json_experimental'

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            **kwargs):
        # The Thrift compiler will make us a `gen-json_experimental`
        # directory per `.thrift` source file.  Use the input filename as
        # the keys to keep them from colliding in `merge_sources_map`.
        return collections.OrderedDict([(thrift_src, 'gen-json_experimental')])

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):

        generator_binary = \
            '$(exe //tupperware/thriftdoc/validator:generate_thriftdoc_ast)'
        source_suffix = '=gen-json_experimental'

        py_library_srcs = {}

        # `sources_map` has genrules that produce `json_experimental`
        # outputs.  This loop feeds their outputs into genrules that convert
        # each JSON into a PAR-includable `thriftdoc_ast.py` file, to be
        # collated into a `python_library` at the very end.
        for thrift_filename, json_experimental_rule in \
                self.merge_sources_map(sources_map).iteritems():
            # This genrule will end up writing its output here:
            #
            #   base_path/
            #     ThriftRule-thriftdoc-py-SourceFile.thrift=thriftdoc_ast.py/
            #       thriftdoc_ast.py
            #
            # The `=thriftdoc_ast.py` suffix is used to differentiate our
            # output from the Thrift-generated target named:
            #
            #   ThriftRuleName-thriftdoc-py-SourceFile.thrift
            #
            # In contrast to `gen_srcs`, nothing splits the rule name on `='.
            assert json_experimental_rule.endswith(source_suffix)
            thriftdoc_rule = json_experimental_rule.replace(
                source_suffix, '=' + self.AST_FILE
            )

            assert thrift_filename.endswith('.thrift')
            # The output filename should be unique in our Python library's
            # linktree, and should be importable from Python.  The filename
            # below is a slight modification of the `.thrift` file's
            # original fbcode path, so it will be unique.  We could
            # guarantee a Python-safe path using `py_base_module` for the
            # base, but this does not seem worth it -- almost all paths in
            # fbcode are Python-safe.
            output_file = os.path.join(
                base_path,
                thrift_filename[:-len('.thrift')],
                self.AST_FILE,
            )
            assert output_file not in py_library_srcs
            py_library_srcs[output_file] = thriftdoc_rule

            assert thriftdoc_rule.startswith(':')
            yield Rule('genrule', collections.OrderedDict(
                name=thriftdoc_rule[1:],  # Get rid of the initial ':',
                out=self.AST_FILE,
                srcs=[json_experimental_rule],
                cmd=' && '.join([
                    # json_experimental gives us a single source file at the
                    # moment.  Should that ever change, the JSON generator
                    # will get an unknown positional arg, and fail loudly.
                    generator_binary + ' --format py > "$OUT" < "$SRCS"/*',
                ]),
            ))
        if self.typing_config_target:
            yield self.gen_typing_config(name)
        yield Rule('python_library', collections.OrderedDict(
            name=name,
            # tupperware.thriftdoc.validator.registry recursively loads this:
            base_module='tupperware.thriftdoc.generated_asts',
            srcs=self.convert_source_map(base_path, py_library_srcs),
            deps=deps,
        ))


RUST_KEYWORDS = {
    "abstract", "alignof", "as", "become", "box",
    "break", "const", "continue", "crate", "do",
    "else", "enum", "extern", "false", "final",
    "fn", "for", "if", "impl", "in",
    "let", "loop", "macro", "match", "mod",
    "move", "mut", "offsetof", "override", "priv",
    "proc", "pub", "pure", "ref", "return",
    "Self", "self", "sizeof", "static", "struct",
    "super", "trait", "true", "type", "typeof",
    "unsafe", "unsized", "use", "virtual", "where",
    "while", "yield",
}


class RustThriftConverter(ThriftLangConverter):
    """
    Specializer to support generating Rust libraries from thrift sources.
    This is a two-stage process; we use the Haskell hs2 compiler to generate
    a JSON representation of the AST, and then a Rust code generator to
    generate code from that.

    Here, the "compiler" is the .thrift -> .ast (json) conversion, and the
    language rule is ast -> {types, client, server, etc crates} -> unified crate
    where the unified crate simply re-exports the other crates (the other
    crates are useful for downstream dependencies which don't need everything)
    """

    def __init__(self, context, *args, **kwargs):
        super(RustThriftConverter, self).__init__(context, *args, **kwargs)
        self._rust_converter = rust.RustConverter(context, 'rust_library')

    def get_lang(self):
        return "rust"

    def get_compiler(self):
        return self._context.config.get_thrift_hs2_compiler()

    def get_compiler_args(
            self,
            flags,
            options,
            hs_required_symbols=None,
            **kwargs):
        args = ["--emit-json", "--rust"]

        # Format the options and pass them into the hs2 compiler.
        for option, val in options.iteritems():
            flag = '--' + option
            if val is not None:
                flag += '=' + val
            args.append(flag)

        # Include rule-specific flags.
        args.extend(filter(lambda a: a not in ['--strict'], flags))

        return args

    def get_generated_sources(
            self,
            base_path,
            name,
            thrift_src,
            services,
            options,
            rs_namespace=None,
            **kwargs):
        thrift_base = (
            os.path.splitext(
                os.path.basename(self.get_source_name(thrift_src)))[0])
        namespace = rs_namespace or ''

        genfiles = ["%s.ast" % thrift_base]

        return collections.OrderedDict(
            [(path, path) for path in
                [os.path.join(namespace, genfile) for genfile in genfiles]])

    def get_ast_to_rust(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):
        sources = self.merge_sources_map(sources_map).values()

        attrs = collections.OrderedDict()
        attrs['name'] = '%s-gen-rs' % name
        attrs['out'] = '%s/%s/lib.rs' % (os.curdir, name)
        attrs['srcs'] = sources
        attrs['cmd'] = '$(exe //common/rust/thrift/compiler:codegen) {} -o $OUT; /bin/rustfmt $OUT' \
            .format(' '.join(['$(location %s)' % s for s in sources]))

        # generated file: <name>/lib.rs

        return [Rule('genrule', attrs)]

    def get_rust_to_rlib(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):

        thrift_base = (
            os.path.splitext(
                os.path.basename(self.get_source_name(thrift_srcs.keys()[0])))[0])

        out_deps = [
            '//common/rust/thrift/runtime:rust_thrift',
        ]
        out_external_deps = [
            ('rust-crates-io', None, 'error-chain'),
            ('rust-crates-io', None, 'futures'),
            ('rust-crates-io', None, 'lazy_static'),
            ('rust-crates-io', None, 'tokio-service'),
        ]

        out_deps += deps

        # Avoid some common names which are also Rust keywords
        crate_name = thrift_base
        if crate_name in RUST_KEYWORDS:
            crate_name += "_"

        return self._rust_converter.convert(
            base_path,
            name,
            srcs=[':%s-gen-rs' % name],
            deps=out_deps,
            external_deps=out_external_deps,
            unittests=False,    # nothing meaningful
            crate=crate_name,
            **kwargs
        )

    def get_language_rule(
            self,
            base_path,
            name,
            thrift_srcs,
            options,
            sources_map,
            deps,
            **kwargs):
        # Construct some rules:
        # json -> rust
        # rust -> rlib

        rules = []

        rules.extend(
            self.get_ast_to_rust(
                base_path, name, thrift_srcs, options, sources_map, deps, **kwargs))
        rules.extend(
            self.get_rust_to_rlib(
                base_path, name, thrift_srcs, options, sources_map, deps, **kwargs))

        return rules


class ThriftLibraryConverter(base.Converter):

    def __init__(self, context):
        super(ThriftLibraryConverter, self).__init__(context)

        # Setup the macro converters.
        converters = [
            CppThriftConverter(context, is_cpp2=False),
            CppThriftConverter(context, is_cpp2=True),
            DThriftConverter(context),
            GoThriftConverter(context),
            HaskellThriftConverter(context, is_hs2=False),
            HaskellThriftConverter(context, is_hs2=True),
            JsThriftConverter(context),
            OCamlThriftConverter(context),
            RustThriftConverter(context),
            ThriftdocPythonThriftConverter(context),
            Python3ThriftConverter(context),
            LegacyPythonThriftConverter(
                context,
                flavor=LegacyPythonThriftConverter.NORMAL),
            LegacyPythonThriftConverter(
                context,
                flavor=LegacyPythonThriftConverter.ASYNCIO),
            LegacyPythonThriftConverter(
                context,
                flavor=LegacyPythonThriftConverter.TWISTED),
            LegacyPythonThriftConverter(
                context,
                flavor=LegacyPythonThriftConverter.PYI),
            LegacyPythonThriftConverter(
                context,
                flavor=LegacyPythonThriftConverter.PYI_ASYNCIO),
        ]
        if use_internal_java_converters:
            converters += [
                JavaDeprecatedApacheThriftConverter(context),
                JavaDeprecatedThriftConverter(context),
                JavaSwiftConverter(context),
            ]
        self._converters = {}
        self._name_to_lang = {}
        for converter in converters:
            self._converters[converter.get_lang()] = converter
            for name in converter.get_names():
                self._name_to_lang[name] = converter.get_lang()

        self._py_converter = python.PythonConverter(context, 'python_binary')

    def get_fbconfig_rule_type(self):
        return 'thrift_library'

    def get_buck_rule_type(self):
        return 'thrift_library'

    def get_languages(self, names):
        """
        Convert the `languages` parameter to a normalized list of languages.
        """

        languages = set()

        if names is None:
            raise TypeError('thrift_library() requires languages argument')

        for name in names:
            lang = self._name_to_lang.get(name)
            if lang is None:
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
        for name, services in sorted(srcs.iteritems()):
            if services is None:
                services = []
            elif not isinstance(services, (tuple, list)):
                services = [services]
            new_srcs[name] = services
        return new_srcs

    def generate_py_remotes(
        self,
        base_path,
        name,
        thrift_srcs,
        base_module,
        include_sr=False
    ):
        """
        Generate all the py-remote rules.
        """

        remotes = []

        # Find and normalize the base module.
        if base_module is None:
            base_module = base_path
        base_module = base_module.replace(os.sep, '.')

        for thrift_src, services in thrift_srcs.iteritems():
            thrift_base = (
                os.path.splitext(
                    os.path.basename(self.get_source_name(thrift_src)))[0])
            for service in services:
                attrs = collections.OrderedDict()
                attrs['name'] = '{}-{}-pyremote'.format(name, service)
                attrs['py_version'] = '<3'
                attrs['base_module'] = ''
                attrs['main_module'] = '.'.join(filter(bool, [
                    base_module,
                    thrift_base,
                    service + '-remote',
                ]))
                if include_sr:
                    sr_rule = 'thrift/facebook/remote/sr'
                else:
                    sr_rule = 'thrift/lib/py/util'
                attrs['deps'] = [
                    ':{}-py'.format(name),
                    '//{}:remote'.format(sr_rule),
                ]
                attrs['external_deps'] = [
                    'python-future',
                    'six',
                ]
                remotes.extend(
                    self._py_converter.convert(
                        base_path,
                        **attrs))

        return remotes

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
            postprocess_cmd=None):
        """
        Generate a rule which runs the thrift compiler for the given inputs.
        """

        attrs = collections.OrderedDict()
        attrs['name'] = (
            '{}-{}-{}'.format(name, lang, self.get_source_name(source)))
        attrs['out'] = os.curdir
        attrs['srcs'] = [source]

        cmds = []

        cmds.append(
            ' '.join(
                self._converters[lang].get_compiler_command(
                    compiler,
                    compiler_args,
                    self.get_exported_include_tree(':' + name))))

        if postprocess_cmd is not None:
            cmds.append(postprocess_cmd)

        attrs['cmd'] = ' && '.join(cmds)

        return Rule('genrule', attrs)

    def generate_generated_source_rules(self, compile_name, srcs):
        """
        Create rules to extra individual sources out of the directory of thrift
        sources the compiler generated.
        """

        out = collections.OrderedDict()
        rules = []

        for name, src in srcs.iteritems():
            attrs = collections.OrderedDict()
            attrs['name'] = '{}={}'.format(compile_name, src)
            attrs['out'] = src
            attrs['cmd'] = ' && '.join([
                'mkdir -p `dirname $OUT`',
                'cp -R $(location :{})/{} $OUT'.format(compile_name, src),
            ])
            rules.append(Rule('genrule', attrs))
            out[name] = ':' + attrs['name']

        return out, rules

    def convert_macros(
            self,
            base_path,
            name,
            thrift_srcs={},
            thrift_args=(),
            deps=(),
            external_deps=(),
            languages=None,
            **kwargs):
        """
        Thrift library conversion implemented purely via macros (i.e. no Buck
        support).
        """

        rules = []

        # Parse incoming options.
        thrift_srcs = self.fixup_thrift_srcs(thrift_srcs)
        thrift_args = self.parse_thrift_args(thrift_args)
        languages = self.get_languages(languages)
        deps = [self.convert_build_target(base_path, d) for d in deps]

        # Setup the exported include tree to dependents.
        includes = set()
        includes.update(thrift_srcs.keys())
        for lang in languages:
            converter = self._converters[lang]
            includes.update(converter.get_extra_includes(**kwargs))
        rules.append(
            self.generate_merge_tree_rule(
                base_path,
                self.get_exported_include_tree(name),
                sorted(includes),
                map(self.get_exported_include_tree, deps)))

        # py3 thrift requires cpp2
        if 'py3' in languages and 'cpp2' not in languages:
            languages.add('cpp2')

        # cpp2 depends on cpp for compatibility mode
        # also save cpp2_options for later use by 'py3'
        if 'cpp2' in languages:
            cpp2_options = (
                self.parse_thrift_options(
                    kwargs.get('thrift_cpp2_options', ())))

            if 'cpp' not in languages and 'compatibility' in cpp2_options:
                languages.add('cpp')

        # Types are generated for all legacy Python Thrift
        if 'py' in languages:
            languages.add('pyi')

        if 'py-asyncio' in languages:
            languages.add('pyi-asyncio')

        # Generate rules for all supported languages.
        for lang in languages:
            converter = self._converters[lang]
            compiler = converter.get_compiler()
            options = (
                self.parse_thrift_options(
                    kwargs.get('thrift_{}_options'.format(
                        lang.replace('-', '_')), ())))
            if lang == 'py3':
                options.update(cpp2_options)
            all_gen_srcs = collections.OrderedDict()
            for thrift_src, services in thrift_srcs.iteritems():
                thrift_name = self.get_source_name(thrift_src)

                # Generate the thrift compile rules.
                compile_rule = (
                    self.generate_compile_rule(
                        base_path,
                        name,
                        compiler,
                        lang,
                        converter.get_compiler_args(
                            thrift_args,
                            converter.get_options(base_path, options),
                            **kwargs),
                        thrift_src,
                        converter.get_postprocess_command(
                            base_path,
                            thrift_name,
                            '$OUT',
                            **kwargs)))
                rules.append(compile_rule)

                # Create wrapper rules to extract individual generated sources
                # and expose via target refs in the UI.
                gen_srcs = (
                    converter.get_generated_sources(
                        base_path,
                        name,
                        thrift_name,
                        services,
                        options,
                        **kwargs))
                gen_srcs, gen_src_rules = (
                    self.generate_generated_source_rules(
                        compile_rule.attributes['name'],
                        gen_srcs))
                all_gen_srcs[thrift_name] = gen_srcs
                rules.extend(gen_src_rules)

            # Generate the per-language rules.
            rules.extend(
                converter.get_language_rule(
                    base_path,
                    name + '-' + lang,
                    thrift_srcs,
                    options,
                    all_gen_srcs,
                    [dep + '-' + lang for dep in deps],
                    **kwargs))
        return rules

    def get_allowed_args(self):
        """
        Return the list of allowed arguments.
        """

        allowed_args = set([
            'cpp2_compiler_flags',
            'cpp2_deps',
            'cpp2_external_deps',
            'cpp2_headers',
            'cpp2_srcs',
            'cpp_compiler_flags',
            'cpp_deps',
            'cpp_headers',
            'cpp_external_deps',
            'cpp_srcs',
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
            'java_thrift_maven_coords',
            'java_swift_maven_coords',
            'languages',
            'name',
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

    def convert(self, base_path, name=None, languages=None, **kwargs):
        rules = []

        supported_languages = self.read_list('thrift', 'supported_languages')
        if supported_languages is not None:
            languages = set(languages) & set(supported_languages)

        # Convert rules we support via macros.
        macro_languages = self.get_languages(languages)
        if macro_languages:
            rules.extend(self.convert_macros(base_path, name=name, languages=languages, **kwargs))

        # If python is listed in languages, then also generate the py-remote
        # rules.
        if 'py' in languages or 'python' in languages:
            rules.extend(
                self.generate_py_remotes(
                    base_path,
                    name,
                    self.fixup_thrift_srcs(kwargs.get('thrift_srcs', {})),
                    kwargs.get('py_base_module'),
                    include_sr=kwargs.get('py_remote_service_router', False)))

        return rules
