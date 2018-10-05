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

# TODO(T20914511): Until the macro lib has been completely ported to
# `include_defs()`, we need to support being loaded via both `import` and
# `include_defs()`.  These ugly preamble is thus here to consistently provide
# `allow_unsafe_import()` regardless of how we're loaded.
import contextlib
try:
    allow_unsafe_import
except NameError:
    @contextlib.contextmanager
    def allow_unsafe_import(*args, **kwargs):
        yield

import collections
import itertools
import pipes
import re

with allow_unsafe_import():
    from distutils.version import LooseVersion
    import os
    import platform as plat
    import shlex

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/cxx_sources.py".format(macro_root), "cxx_sources")
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("{}:fbcode_target.py".format(macro_root),
     "RootRuleTarget",
     "RuleTarget",
     "ThirdPartyRuleTarget")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:modules.bzl", "modules")
load("@fbcode_macros//build_defs:auto_headers.bzl", "AutoHeaders")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")


LEX = ThirdPartyRuleTarget('flex', 'flex')
LEX_LIB = ThirdPartyRuleTarget('flex', 'fl')

YACC = ThirdPartyRuleTarget('bison', 'bison')
YACC_FLAGS = ['-y', '-d']


# A regex matching preprocessor flags trying to pull in system include paths.
# These are bad as they can cause headers for system packages to mask headers
# from third-party.
SYS_INC = re.compile('^(?:-I|-isystem)?/usr(?:/local)?/include')


def create_dll_needed_syms_list_rule(name, dlls, visibility):
    attrs = collections.OrderedDict()
    attrs['name'] = '{}-syms'.format(name)
    if visibility is not None:
        attrs['visibility'] = visibility
    attrs['out'] = 'symbols.txt'
    attrs['cmd'] = (
        'nm -gPu {} | awk \'{{print $1}}\' | '
        'grep -v ^BuildInfo_k | sort > $OUT'
        .format(' '.join(['$(location {})'.format(d) for d in dlls])))
    return Rule('cxx_genrule', attrs)


def create_dll_syms_linker_script_rule(name, symbols_rule, visibility):
    attrs = collections.OrderedDict()
    attrs['name'] = '{}-syms-linker-script'.format(name)
    if visibility is not None:
        attrs['visibility'] = visibility
    attrs['out'] = 'extern_symbols.txt'
    attrs['cmd'] = (
        'cat $(location {}) | awk \'{{print "EXTERN("$1")"}}\' > "$OUT"'
        .format(symbols_rule))
    return Rule('cxx_genrule', attrs)


def create_dll_syms_dynamic_list_rule(name, symbols_rule, visibility):
    attrs = collections.OrderedDict()
    attrs['name'] = '{}-syms-dynamic-list'.format(name)
    if visibility is not None:
        attrs['visibility'] = visibility
    attrs['out'] = 'extern_symbols.txt'
    attrs['cmd'] = ' && '.join([
        'echo "{" > $OUT',
        'cat $(location {}) | awk \'{{print "  "$1";"}}\' >> "$OUT"'
        .format(symbols_rule),
        'echo "};" >>$OUT',
    ])
    return Rule('cxx_genrule', attrs)


def create_dll_rules(
        name,
        lib_name,
        dll_root,
        rule_type_filter,
        rule_name_filter,
        dll_type,
        fbcode_dir,
        visibility):
    """
    Create a rule to link a DLL.
    """

    rules = []

    cmd = []
    cmd.append('$(ld)')

    # Build a shared library.
    if dll_type == 'static' or dll_type == 'static-pic':
        cmd.append('-r')
    elif dll_type == 'shared':
        cmd.append('-shared')
    else:
        raise AttributeError(
                'dll_type must be one of static, static-pic or shared')
    cmd.append('-nostdlib')
    cmd.extend(['-o', '$OUT'])

    # When GHC links DSOs, it sets this flag to prevent non-PIC symbols
    # from leaking to the dynamic symbol table, as it breaks linking.
    cmd.append('-Wl,-Bsymbolic')

    # Add-in the macro to add the transitive deps to the link line.  For
    # shared link styles, we do a shared link, but for anything else (i.e.
    # static, static-pic), we always do a `static` link, as we need to
    # support profiled builds with DSOs and this requires that we issue
    # an `-hisuf p_hi`, which we can't supply in addition to the 'dyn_hi'
    # suffix that a `-dynamic -fPIC` (i.e. static-pic) compilation rquires.
    # This is fine for GHC-built DSOs. To quote https://fburl.com/ze4ni010:
    # "Profiled code isn't yet really position-independent even when -fPIC
    # is specified. Building profiled dynamic libraries therefore fails on
    # Mac OS X (Linux silently accepts relocations - it's just slightly bad
    # for performance)." We also set a "filter" here so we only get haskell
    # rules in the link.
    if dll_type == 'shared' or dll_type == 'static-pic':
        dll_type_filter = 'ldflags-static-pic-filter'
    else: # 'static'
        dll_type_filter = 'ldflags-static-filter'
    cmd.append(
        '$({} ^{}[(]{}[)]$ {})'
        .format(
            dll_type_filter,
            rule_type_filter or '.*',
            rule_name_filter or '.*',
            dll_root))

    attributes = collections.OrderedDict()
    attributes['name'] = name
    if visibility is not None:
        attributes['visibility'] = visibility
    attributes['out'] = lib_name
    fbcode = os.path.join('$GEN_DIR', fbcode_dir)
    attributes['cmd'] = 'cd {} && '.format(fbcode) + ' '.join(cmd)
    rules.append(Rule('cxx_genrule', attributes))

    return rules

# TODO: Remove the default value when haskell rules get converted
def convert_dlls(
        base_path,
        name,
        platform,
        buck_platform,
        dlls,
        fbcode_dir,
        visibility=None):
    """
    """

    assert dlls

    rules = []
    deps = []
    ldflags = []
    dep_queries = []

    # Generate the rules that link the DLLs.
    dll_targets = {}
    for dll_lib_name, (dll_root, type_filter, name_filter, dll_type) in dlls.items():
        dll_name = name + '.' + dll_lib_name
        dll_targets[dll_lib_name] = ':' + dll_name
        rules.extend(
            create_dll_rules(
                dll_name,
                dll_lib_name,
                dll_root + '-dll-root',
                type_filter,
                name_filter,
                dll_type,
                fbcode_dir,
                visibility))

    # Create the rule which extracts the symbols from all DLLs.
    sym_rule = (
        create_dll_needed_syms_list_rule(name, dll_targets.values(), visibility))
    sym_target = ':{}'.format(sym_rule.attributes['name'])
    rules.append(sym_rule)

    # Create the rule which sets up a linker script with all missing DLL
    # symbols marked as extern.
    syms_linker_script = (
        create_dll_syms_linker_script_rule(name, sym_target, visibility))
    rules.append(syms_linker_script)
    ldflags.append(
        '$(location :{})'
        .format(syms_linker_script.attributes['name']))

    # Make sure all symbols needed by the DLLs are exported to the binary's
    # dynamic symbol table.
    ldflags.append('-Xlinker')
    ldflags.append('--export-dynamic')

    # Form a sub-query which matches all deps relevant to the current
    # platform.
    first_order_dep_res = [
        # Match any non-third-party deps.
        '(?!//third-party-buck/.{0,100}).*',
        # Match any third-party deps for the current platform.
        '//third-party-buck/{0}/.*'.format(platform),
    ]

    # Form a sub-query to exclude all of the generated-lib deps, in particular
    # sanitizer-configuration libraries
    generated_lib = r'(?<!{})'.format(base.GENERATED_LIB_SUFFIX)
    first_order_deps = (
        'filter("^({prefix}){exclude_generated}$", first_order_deps())'
        .format(
            prefix='|'.join('(' + r + ')' for r in first_order_dep_res),
            exclude_generated=generated_lib,
        )
    )

    # Form a query which resolve to all the first-order deps of all DLLs.
    # These form roots which need to be linked into the top-level binary.
    dll_deps = []
    for dll_lib_name, (_, type_filter, name_filter, _) in dlls.items():
        dll_nodes = (
            # The `deps` function's second argument is the depth of the
            # search and while we don't actually want to override its
            # default value, we need to set it in order to use the third
            # argument, so just set it to some arbitrarily high value.
            'deps({root}, 4000,'
            ' kind("^{type_filter}$",'
            '  filter("^{name_filter}$",'
            '   {deps})))'
            .format(
                root='//{}:{}.{}'.format(base_path, name, dll_lib_name),
                type_filter=type_filter or '.*',
                name_filter=name_filter or '.*',
                deps=first_order_deps))
        # We need to link deep on Haskell libraries because of cross-module
        # optimizations like inlining.
        # Eg. we import A, inline something from A that refers to B and now
        # have a direct symbol reference to B.
        dll_deps.append(
            'deps('
            ' deps({nodes}, 4000, kind("haskell_library", {first_order_deps})),'
            ' 1,'
            ' kind("library", {first_order_deps}))'
            '- {nodes}'
            .format(nodes=dll_nodes,first_order_deps=first_order_deps))
    dep_query = ' union '.join('({})'.format(d) for d in dll_deps)
    dep_queries.append(dep_query)
    # This code is currently only used for Haskell code in Sigma
    # Search for Note [Sigma hot-swapping code]

    # Create the rule which copies the DLLs into the output location.
    attrs = collections.OrderedDict()
    attrs['name'] = name + '.dlls'
    if visibility is not None:
        attrs['visibility'] = visibility
    attrs['out'] = os.curdir
    cmds = []
    cmds.append('mkdir -p $OUT')
    for dll_name, dll_target in dll_targets.items():
        cmds.append(
            'cp $(location {}) "$OUT"/{}'
            .format(dll_target, dll_name))
    attrs['cmd'] = ' && '.join(cmds)
    rules.append(Rule('cxx_genrule', attrs))
    deps.append(
        RootRuleTarget(
            base_path,
            '{}#{}'.format(attrs['name'], buck_platform)))
    return rules, deps, ldflags, dep_queries


class AbsentParameter(object):
    """
    A marker class which helps us differentiate between empty/falsey/None values
    defaulted in a function's arg list, vs. actually passed in from the caller
    with such a value.
    """

    def __len__(self):
        "If `len` is zero, this is considered falsey by `if (x)` or `bool(x)`."
        return 0


ABSENT = AbsentParameter()


class CppConverter(base.Converter):

    C_SOURCE_EXTS = (
        '.c',
    )

    CPP_SOURCE_EXTS = (
        '.cc',
        '.cpp',
    )

    SOURCE_EXTS = frozenset(C_SOURCE_EXTS + CPP_SOURCE_EXTS)

    HEADER_EXTS = (
        '.h',
        '.tcc',
        '-inl.h',
        '-defs.h',
    )

    LEX_EXTS = (
        '.ll',
    )

    YACC_EXTS = (
        '.yy',
    )

    RULE_TYPE_MAP = {
        'cpp_library': 'cxx_library',
        'cpp_binary': 'cxx_binary',
        'cpp_unittest': 'cxx_test',
        'cpp_benchmark': 'cxx_binary',
        'cpp_node_extension': 'cxx_binary',
        'cpp_precompiled_header': 'cxx_precompiled_header',
        'cpp_python_extension': 'cxx_python_extension',
        # We build C/C++ Java extensions as normal libraries in dev-based
        # modes, and as monolithic dlopen-enabled C/C++ binaries in all other
        # modes.
        'cpp_java_extension':
            lambda mode: (
                'cxx_library' if mode.startswith('dev') else 'cxx_binary'),
        'cpp_lua_extension': 'cxx_lua_extension',
        'cpp_lua_main_module': 'cxx_library',
    }

    def __init__(self, context, rule_type):
        super(CppConverter, self).__init__(context)
        self._rule_type = rule_type

    def is_deployable(self):
        """
        Return whether this rule's output is meant to be deployed outside of
        fbcode.
        """

        return self.get_fbconfig_rule_type() in (
            'cpp_binary',
            'cpp_unittest',
            'cpp_benchmark')

    def is_binary(self, dlopen_info):
        """
        Return whether this rule builds a binary.
        """

        # `dlopen_enabled=True` binaries are really libraries.
        if dlopen_info is not None:
            return False

        return self.is_deployable()

    def is_buck_binary(self):
        return self.get_buck_rule_type() in ('cxx_binary', 'cxx_test')

    def is_library(self):
        return self.get_fbconfig_rule_type() == 'cpp_library'

    def is_extension(self):
        return self.get_fbconfig_rule_type() in (
            'cpp_python_extension',
            'cpp_java_extension',
            'cpp_lua_extension')

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        rule_type = self.RULE_TYPE_MAP[self._rule_type]
        if callable(rule_type):
            rule_type = rule_type(self._context.mode)
        return rule_type

    def split_matching_extensions_and_other(self, srcs, exts):
        """
        Split a list into two based on the extension of the items.

        Returns a tuple (mathing, other), where matching is a list of
        items from srcs whose extensions are in exts and other is a
        list of the remaining items from srcs.
        """

        matches = []
        leftovers = []

        for src in (srcs or []):
            base, ext = os.path.splitext(src)
            if ext in exts:
                matches.append(src)
            else:
                leftovers.append(src)

        return (matches, leftovers)

    def get_headers_from_sources(self, base_path, srcs):
        """
        Return the headers likely associated with the given sources.
        """

        glob = self._context.buck_ops.glob
        source_exts = self.SOURCE_EXTS  # use a local for faster lookups in a loop
        # Check for // in case this src is a rule
        split_srcs = (
            os.path.splitext(src)
            for src in srcs
            if '//' not in src and not src.startswith(':'))

        headers = glob([
            base + hext
            for base, ext in split_srcs if ext in source_exts
            for hext in cxx_sources.HEADER_SUFFIXES])
        return headers

    def get_dlopen_info(self, dlopen_enabled):
        """
        Parse the `dlopen_enabled` parameter into a dictionary.
        """

        dlopen_info = None

        if dlopen_enabled:
            dlopen_info = {}
            if isinstance(dlopen_enabled, str):
                dlopen_info['soname'] = dlopen_enabled
            elif isinstance(dlopen_enabled, dict):
                dlopen_info.update(dlopen_enabled)

        return dlopen_info

    def get_sanitizer_binary_ldflags(self):
        """
        Return any linker flags to use when linking binaries with sanitizer
        support.
        """

        sanitizer = sanitizers.get_sanitizer()
        assert sanitizer is not None

        flags = []

        if sanitizer.startswith('address'):
            flags.append(
                '-Wl,--dynamic-list='
                '$(location fbcode//tools/build/buck:asan_dynamic_list.txt)')

        return flags

    def get_sanitizer_non_binary_deps(self):
        """
        Return deps needed when using sanitizers.
        """

        sanitizer = sanitizers.get_sanitizer()
        assert sanitizer is not None

        deps = []

        # We link ASAN weak stub symbols into every DSO so that we don't leave
        # undefined references to *SAN symbols at shared library link time,
        # which allows us to pass `--no-undefined` to the linker to prevent
        # undefined symbols.
        if (sanitizer.startswith('address') and
                self.get_link_style() == 'shared'):
            deps.append(RootRuleTarget('tools/build/sanitizers', 'asan-stubs'))

        return deps

    def get_coverage_ldflags(self, base_path):
        """
        Return compiler flags needed to support coverage builds.
        """

        flags = []

        coverage = self.is_coverage_enabled(base_path)
        if coverage and sanitizers.get_sanitizer() is None:
            # Add flags to enable LLVM's Coverage Mapping.
            flags.append('-fprofile-instr-generate')
            flags.append('-fcoverage-mapping')

        return flags

    def convert_lex(self, name, lex_flags, lex_src, platform, visibility):
        """
        Create rules to generate a C/C++ header and source from the given lex
        file.
        """

        name_base = '{}={}'.format(name.replace(os.sep, '-'), lex_src)
        header_name = name_base + '.h'
        source_name = name_base + '.cc'

        base = lex_src
        header = base + '.h'
        source = base + '.cc'

        attrs = collections.OrderedDict()
        attrs['name'] = name_base
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = base + '.d'
        attrs['srcs'] = [lex_src]
        attrs['cmd'] = ' && '.join([
            'mkdir -p $OUT',
            '$(exe {lex}) {args} -o$OUT/{src} --header-file=$OUT/{hdr}'
            ' $SRCS'
            .format(
                lex=self.get_tool_target(LEX, platform),
                args=' '.join([pipes.quote(f) for f in lex_flags]),
                src=pipes.quote(source),
                hdr=pipes.quote(header)),
            r"""(cd "$GEN_DIR"/{fbcode} &&"""
            r""" perl -pi -e 's!\Q'"$PWD"'/\E!!' "$OUT"/{src} "$OUT"/{hdr})"""
            .format(
                fbcode=self.get_fbcode_dir_from_gen_dir(),
                src=pipes.quote(source),
                hdr=pipes.quote(header)),
        ])

        rules = []
        rules.append(Rule('genrule', attrs))
        rules.append(
            self.copy_rule(
                '$(location :{})/{}'.format(name_base, header),
                header_name,
                header))
        rules.append(
            self.copy_rule(
                '$(location :{})/{}'.format(name_base, source),
                source_name,
                source))

        return (':' + header_name, ':' + source_name, rules)

    def convert_yacc(self, base_path, name, yacc_flags, yacc_src, platform, visibility):
        """
        Create rules to generate a C/C++ header and source from the given yacc
        file.
        """

        is_cpp = ('--skeleton=lalr1.cc' in yacc_flags)

        name_base = '{}={}'.format(name.replace(os.sep, '-'), yacc_src)
        header_name = name_base + '.h'
        source_name = name_base + '.cc'

        base = yacc_src
        header = base + '.h'
        source = base + '.cc'

        if is_cpp:
            stack_header_name = '{}=stack.hh'.format(name.replace(os.sep, '-'))
            stack_header = 'stack.hh'
        else:
            stack_header = None

        commands = [
            'mkdir -p $OUT',
            '$(exe {yacc}) {args} -o "$OUT/{base}.c" $SRCS',

            # Sanitize the header and source files of original source line-
            # markers and include guards.
            'sed -i'
            r""" -e 's|'"$SRCS"'|'{src}'|g' """
            r""" -e 's|YY_YY_.*_INCLUDED|YY_YY_{defn}_INCLUDED|g' """
            ' "$OUT/{base}.c" "$OUT/{base}.h"',

            # Sanitize the source file of self-referencing line-markers.
            'sed -i'
            r""" -e 's|\b{base}\.c\b|{base}.cc|g' """
            r""" -e 's|'"$OUT"'/'{base}'\.cc\b|'{out_cc}'|g' """
            ' "$OUT/{base}.c"',

            # Sanitize the header file of self-referencing line-markers.
            'sed -i'
            r""" -e 's|'"$OUT"'/'{base}'\.h\b|'{out_h}'|g' """
            ' "$OUT/{base}.h"',
            'mv "$OUT/{base}.c" "$OUT/{base}.cc"'
        ]

        if is_cpp:
            commands.append(
                # Patch the header file to add include header file prefix
                # e.g.: thrifty.yy.h => thrift/compiler/thrifty.yy.h
                'sed -i'
                r""" -e 's|#include "{base}.h"|#include "{base_path}/{base}.h"|g' """
                ' "$OUT/{base}.cc"'
            )
            commands.append(
                # Sanitize the stack header file's line-markers.
                'sed -i'
                r""" -e 's|#\(.*\)YY_YY_[A-Z0-9_]*_FBCODE_|#\1YY_YY_FBCODE_|g' """
                r""" -e 's|#line \([0-9]*\) "/.*/fbcode/|#line \1 "fbcode/|g' """
                r""" -e 's|\\file /.*/fbcode/|\\file fbcode/|g' """
                ' "$OUT/{stack_header}"',
            )

        attrs = collections.OrderedDict()
        attrs['name'] = name_base
        attrs['out'] = base + '.d'
        attrs['srcs'] = [yacc_src]
        attrs['cmd'] = ' && '.join(commands).format(
            yacc=self.get_tool_target(YACC, platform),
            args=' '.join(
                [pipes.quote(f) for f in YACC_FLAGS + list(yacc_flags)]),
            src=pipes.quote(os.path.join(base_path, yacc_src)),
            out_cc=pipes.quote(
                os.path.join(
                    'buck-out',
                    'gen',
                    base_path,
                    base + '.cc',
                    base + '.cc')),
            out_h=pipes.quote(
                os.path.join(
                    'buck-out',
                    'gen',
                    base_path,
                    base + '.h',
                    base + '.h')),
            defn=re.sub('[./]', '_', os.path.join(base_path, header)).upper(),
            base=pipes.quote(base),
            base_path=base_path,
            stack_header=stack_header,
        )

        rules = []
        rules.append(Rule('genrule', attrs))
        rules.append(
            self.copy_rule(
                '$(location :{})/{}'.format(name_base, header),
                header_name,
                header,
                visibility=visibility))
        rules.append(
            self.copy_rule(
                '$(location :{})/{}'.format(name_base, source),
                source_name,
                source,
                visibility=visibility))

        if is_cpp:
            rules.append(
                self.copy_rule(
                    '$(location :{})/{}'.format(name_base, stack_header),
                    stack_header_name,
                    stack_header,
                    visibility=visibility))

        returned_headers = [':' + header_name]
        if is_cpp:
            returned_headers.append(':' + stack_header_name)

        return (returned_headers, ':' + source_name, rules)

    def has_cuda_dep(self, dependencies):
        """
        Returns whether there is any dependency on CUDA tp2.
        """

        for dep in dependencies:
            if dep.repo is not None and dep.base_path == 'cuda':
                return True

        return False

    def is_cuda_src(self, src):
        """
        Return whether this `srcs` entry is a CUDA source file.
        """
        # If this is a generated rule reference, then extract the source
        # name.
        if '=' in src:
            src = src.rsplit('=', 1)[1]

        # Assume generated sources without explicit extensions are non-CUDA
        if src.startswith(('@', ':', '//')):
            return False

        # If the source extension is `.cu` it's cuda.
        _, ext = os.path.splitext(src)
        return ext == '.cu'

    def has_cuda_srcs(self, srcs):
        """
        Return whether this rule has CUDA sources.
        """

        for src in srcs:
            if self.is_cuda_src(src):
                return True
        return False

    def get_lua_base_module_parts(self, base_path, base_module):
        """
        Get the list of base module parts for this rule.
        """

        # If base module is unset, prepare a default.
        if base_module is None:
            return ['fbcode'] + base_path.split(os.sep)

        # If base module is empty, return the empty list.
        elif not base_module:
            return []

        # Otherwise, split it on the module separater.
        else:
            return base_module.split('.')

    def get_lua_base_module(self, base_path, base_module):
        parts = self.get_lua_base_module_parts(base_path, base_module)
        return '.'.join(parts)

    def get_lua_init_symbol(self, base_path, name, base_module):
        parts = self.get_lua_base_module_parts(base_path, base_module)
        return '_'.join(['luaopen'] + parts + [name])

    @classmethod
    def get_auto_headers(cls, headers, auto_headers, read_config):
        """
        Get the level of auto-headers to apply to the rule.
        """

        # If `auto_headers` is set, use that.
        if auto_headers is not None:
            return auto_headers

        # For backwards compatibility, if the `headers` parameter is a string,
        # then it refers to an auto-headers setting.
        if isinstance(headers, basestring):
            return headers

        # If it's `None`, then return the global default.
        return read_config(
            'cxx',
            'auto_headers',
            AutoHeaders.SOURCES)

    def get_implicit_deps(self):
        """
        Add additional dependencies we need to implicitly add to the build for
        various reasons.
        """

        deps = []

        # TODO(#13588666): When using clang with the gcc-5-glibc-2.23 platform,
        # `-latomic` isn't automatically added to the link line, meaning uses
        # of `std::atomic<T>` fail to link with undefined reference errors.
        # So implicitly add this dep here.
        #
        # TODO(#17067102): `cpp_precompiled_header` rules currently don't
        # support `platform_deps` parameter.
        if self.get_fbconfig_rule_type() != 'cpp_precompiled_header':
            deps.append(ThirdPartyRuleTarget('libgcc', 'atomic'))

        return deps

    def verify_linker_flags(self, flags):
        """
        Check for invalid linker flags.
        """

        # PLEASE DON'T UPDATE WITHOUT REACHING OUT TO FBCODE FOUNDATION FIRST.
        # Using arbitrary linker flags in libraries can cause unexpected issues
        # for upstream dependencies, so we make sure to restrict to a safe(r)
        # subset of potential flags.
        prefixes = [
            '-L',
            '-u',
            '-rpath',
            '--wrap',
            '--dynamic-list',
            '--export-dynamic',
            '--enable-new-dtags',
        ]

        for flag in flags:
            if not re.match('|'.join(prefixes), flag):
                raise ValueError(
                    'using disallowed linker flag in a library: ' + flag)

    def verify_preprocessor_flags(self, param, flags):
        """
        Make sure the given flags are valid preprocessor flags.
        """

        # Check that we're getting an actual preprocessor flag (e.g. and not a
        # compiler flag).
        for flag in flags:
            if not re.match('-[DI]', flag):
                raise ValueError(
                    '`{}`: invalid preprocessor flag (expected `-[DI]*`): {}'
                    .format(param, flag))

        # Check for includes pointing to system paths.
        bad_flags = [flag for flag in flags if SYS_INC.search(flag)]
        if bad_flags:
            raise ValueError(
                'The flags \"{}\" in \'preprocessor_flags\' would pull in '
                'system include paths which could cause incompatible '
                'header files to be used instead of correct versions from '
                'third-party.'
                .format(' '.join(bad_flags)))

    @classmethod
    def has_file_ext(cls, filename, extensions):
        return [ext for ext in extensions if filename.endswith(ext)]

    @classmethod
    def is_c_source(cls, filename):
        return cls.has_file_ext(filename, cls.C_SOURCE_EXTS)

    @classmethod
    def is_cpp_source(cls, filename):
        return cls.has_file_ext(filename, cls.CPP_SOURCE_EXTS)

    def convert_rule(
            self,
            base_path,
            name=None,
            base_module=None,
            module_name=None,
            srcs=[],
            src=None,
            deps=[],
            arch_compiler_flags={},
            compiler_flags=(),
            known_warnings=[],
            headers=None,
            header_namespace=None,
            compiler_specific_flags={},
            supports_coverage=None,
            tags=(),
            linker_flags=(),
            arch_preprocessor_flags={},
            preprocessor_flags=(),
            prefix_header=None,
            precompiled_header=ABSENT,
            propagated_pp_flags=(),
            link_whole=None,
            global_symbols=[],
            allocator=None,
            args=None,
            external_deps=[],
            type='gtest',
            owner=None,
            emails=None,
            dlopen_enabled=None,
            nodefaultlibs=False,
            shared_system_deps=None,
            system_include_paths=None,
            split_symbols=None,
            env=None,
            use_default_test_main=True,
            lib_name=None,
            nvcc_flags=(),
            enable_lto=False,
            hs_profile=None,
            dont_link_prerequisites=None,
            lex_args=(),
            yacc_args=(),
            runtime_files=(),
            additional_coverage_targets=(),
            embed_deps=True,
            py3_sensitive_deps=(),
            timeout=None,
            dlls={},
            versions=None,
            visibility=None,
            auto_headers=None,
            preferred_linkage=None,
            os_deps=None,
            os_linker_flags=None,
            autodeps_keep=False,
            undefined_symbols=False,
            module=None,
            compile_with_modules=None):

        if not isinstance(compiler_flags, (list, tuple)):
            raise TypeError(
                "Expected compiler_flags to be a list or a tuple, got {0!r} instead.".
                format(compiler_flags)
            )

        # autodeps_keep is used by dwyu/autodeps and ignored by infra_macros.
        extra_rules = []
        out_srcs = []  # type: List[SourceWithFlags]
        out_headers = []
        out_exported_ldflags = []
        out_ldflags = []
        out_dep_queries = []
        dependencies = []
        os_deps = os_deps or []
        os_linker_flags = os_linker_flags or []
        out_link_style = self.get_link_style()
        build_mode = self.get_build_mode()
        dlopen_info = self.get_dlopen_info(dlopen_enabled)
        exported_lang_pp_flags = collections.defaultdict(list)
        platform = (
            self.get_platform(
                base_path
                if self.get_fbconfig_rule_type() != 'cpp_node_extension'
                # Node rules always use the platforms set in the root PLATFORM
                # file.
                else ''))

        cuda = self.has_cuda_srcs(srcs)

        # TODO(lucian, pbrady, T24109997): temp hack until platform007 has full CUDA support.
        # Until then unblock migration to p007 for projects that don't really need CUDA,
        # but depend on CUDA through convenience transitive dependencies.
        # Once platform007 supports CUDA cuda_deps should be merged back into deps.
        if platform.startswith('platform007'):
            def filter_flags(flags):
                banned_flags = ['-DUSE_CUDNN=1', '-DUSE_CUDNN', '-DCAFFE2_USE_CUDNN']
                return [f for f in flags if f not in banned_flags]

            def filter_flags_dict(flags_dict):
                if flags_dict is None:
                    return None
                ret = {}
                for compiler, flags in flags_dict.items():
                    ret[compiler] = filter_flags(flags)
                return ret

            compiler_flags = filter_flags(compiler_flags)
            preprocessor_flags = filter_flags(preprocessor_flags)
            propagated_pp_flags = filter_flags(propagated_pp_flags)
            nvcc_flags = filter_flags(nvcc_flags)
            arch_compiler_flags = filter_flags_dict(arch_compiler_flags)
            arch_preprocessor_flags = filter_flags_dict(arch_preprocessor_flags)

            banned_cuda_srcs_re = [re.compile(pattern) for pattern in [
                "caffe2/caffe2/.*cudnn.cc",
                "caffe2/caffe2/.*gpu.cc",
                "caffe2/caffe2/contrib/nervana/.*gpu.cc",
                "caffe2/caffe2/operators/.*cudnn.cc",
                "caffe2/caffe2/fb/operators/scale_gradient_op_gpu.cc",
                "caffe2/caffe2/fb/predictor/PooledPredictor.cpp",
                "caffe2/caffe2/fb/predictor/PredictorGPU.cpp",
            ]]

            def is_banned_src(src):
                return any(r.match(src) for r in banned_cuda_srcs_re)

            cuda_srcs = [s for s in srcs if self.is_cuda_src(s) or is_banned_src(base_path + '/' + s)]
            srcs = [s for s in srcs if s not in cuda_srcs]
            cuda = False
            if cuda_srcs:
                print('Warning: no CUDA on platform007: rule {}:{} ignoring cuda_srcs: {}'
                      .format(base_path, name, cuda_srcs))

        # Figure out whether this rule's headers should be built into a clang
        # module (in supporting build modes).
        out_module = True
        # Check the global, build mode default.
        global_modules = self.read_bool('cxx', 'module_rule_default', required=False)
        if global_modules is not None:
            out_module = global_modules
        # Check the build mode file override.
        if build_mode is not None and build_mode.cxx_modules is not None:
            out_module = build_mode.cxx_modules
        # Check the rule override.
        if module is not None:
            out_module = module

        # Figure out whether this rule should be built using clang modules (in
        # supporting build modes).
        out_compile_with_modules = True
        # Check the global, build mode default.
        global_compile_with_modules = (
            self.read_bool('cxx', 'compile_with_modules', required=False))
        if global_compile_with_modules is not None:
            compile_with_modules = global_compile_with_modules
        # Check the build mode file override.
        if (build_mode is not None and
                build_mode.cxx_compile_with_modules is not None):
            out_compile_with_modules = build_mode.cxx_compile_with_modules
        # Check the rule override.
        if compile_with_modules is not None:
            out_compile_with_modules = compile_with_modules
        # Don't build precompiled headers with modules.
        if self.get_fbconfig_rule_type() == 'cpp_precompiled_header':
            out_compile_with_modules = False

        attributes = collections.OrderedDict()

        attributes['name'] = name

        if visibility is not None:
            attributes['visibility'] = visibility

        # Set the base module.
        rule_type = self.get_fbconfig_rule_type()
        if rule_type == 'cpp_lua_extension':
            attributes['base_module'] = (
                self.get_lua_base_module(base_path, base_module))
        elif rule_type == 'cpp_python_extension' and base_module is not None:
            attributes['base_module'] = base_module

        if module_name is not None:
            attributes['module_name'] = module_name

        if self.is_library():
            if preferred_linkage:
                attributes['preferred_linkage'] = preferred_linkage
            if link_whole:
                attributes['link_whole'] = link_whole
            if global_symbols:
                if platform_utils.get_platform_architecture(
                        self.get_platform(base_path)) == 'aarch64':
                    # On aarch64 we use bfd linker which doesn't support
                    # --export-dynamic-symbol. We force link_whole instead.
                    attributes['link_whole'] = True
                else:
                    flag = ('undefined' if out_link_style == 'static' else
                            'export-dynamic-symbol')
                    out_exported_ldflags = ['-Wl,--%s,%s' % (flag, sym)
                                            for sym in global_symbols]

        # Parse the `header_namespace` parameter.
        if header_namespace is not None:
            if (base_path, name) not in self._context.config.get_header_namespace_whitelist() and not any(
                # Check base path prefix in header_namespace_whitelist
                len(t) == 1 and base_path.startswith(t[0])
                for t in self._context.config.get_header_namespace_whitelist()
            ):
                raise ValueError(
                    '{}(): the `header_namespace` parameter is *not* '
                    'supported in fbcode -- `#include` paths must match '
                    'their fbcode-relative path. ({}/{})'
                    .format(self.get_fbconfig_rule_type(), base_path, name))
            out_header_namespace = header_namespace
        else:
            out_header_namespace = base_path

        # Form compiler flags.  We pass everything as language-specific flags
        # so that we can can control the ordering.
        out_lang_plat_compiler_flags = self.get_compiler_flags(base_path)
        for lang in self.get_compiler_langs():
            out_lang_plat_compiler_flags.setdefault(lang, [])
            out_lang_plat_compiler_flags[lang].extend(
                self.format_platform_param(compiler_flags))
            out_lang_plat_compiler_flags[lang].extend(
                self.format_platform_param(
                    lambda _, compiler:
                        compiler_specific_flags.get(
                            'gcc' if cuda else compiler)))
        out_lang_plat_compiler_flags.setdefault('cuda_cpp_output', [])
        out_lang_plat_compiler_flags['cuda_cpp_output'].extend(
            self.format_platform_param(
                list(itertools.chain(
                    *[('-_NVCC_', flag) for flag in nvcc_flags]))))

        clang_profile = self._context.buck_ops.read_config('cxx', 'profile')
        if clang_profile is not None:
            compiler.require_global_compiler(
                "cxx.profile only supported by modes using clang globally",
                "clang")
            profile_args = [
                '-fprofile-sample-use=$(location {})'.format(clang_profile),
                '-fdebug-info-for-profiling',
                # '-fprofile-sample-accurate'
            ]
            out_lang_plat_compiler_flags['c_cpp_output'].extend(
                self.format_platform_param(profile_args))
            out_lang_plat_compiler_flags['cxx_cpp_output'].extend(
                self.format_platform_param(profile_args))

        if out_lang_plat_compiler_flags:
            attributes['lang_platform_compiler_flags'] = (
                out_lang_plat_compiler_flags)

        # Form platform-specific compiler flags.
        out_platform_compiler_flags = []
        out_platform_compiler_flags.extend(
            self.get_platform_flags_from_arch_flags(arch_compiler_flags))
        if out_platform_compiler_flags:
            attributes['platform_compiler_flags'] = (
                out_platform_compiler_flags)

        # Form preprocessor flags.
        out_preprocessor_flags = []
        if not cuda:
            if sanitizers.get_sanitizer() is not None:
                out_preprocessor_flags.extend(sanitizers.get_sanitizer_flags())
            out_preprocessor_flags.extend(self.get_coverage_flags(base_path))
        self.verify_preprocessor_flags(
            'preprocessor_flags',
            preprocessor_flags)
        out_preprocessor_flags.extend(preprocessor_flags)
        if self.get_fbconfig_rule_type() == 'cpp_lua_main_module':
            out_preprocessor_flags.append('-Dmain=lua_main')
            out_preprocessor_flags.append(
                '-includetools/make_lar/lua_main_decl.h')
        if self.get_fbconfig_rule_type() == 'cpp_lua_extension':
            out_preprocessor_flags.append(
                '-DLUAOPEN={}'.format(
                    self.get_lua_init_symbol(base_path, name, base_module)))
        if out_preprocessor_flags:
            attributes['preprocessor_flags'] = out_preprocessor_flags
        if prefix_header:
            attributes['prefix_header'] = prefix_header

        # Form language-specific preprocessor flags.
        out_lang_preprocessor_flags = collections.defaultdict(list)
        if build_mode is not None:
            if build_mode.aspp_flags:
                out_lang_preprocessor_flags['assembler_with_cpp'].extend(
                    build_mode.aspp_flags)
            if build_mode.cpp_flags:
                out_lang_preprocessor_flags['c'].extend(
                    build_mode.cpp_flags)
            if build_mode.cxxpp_flags:
                out_lang_preprocessor_flags['cxx'].extend(
                    build_mode.cxxpp_flags)
        out_lang_preprocessor_flags['c'].extend(
            self.get_extra_cppflags())
        out_lang_preprocessor_flags['cxx'].extend(
            self.get_extra_cxxppflags())
        out_lang_preprocessor_flags['assembler_with_cpp'].extend(
            self.get_extra_cxxppflags())
        if modules.enabled() and out_compile_with_modules:
            # Add module toolchain flags.
            out_lang_preprocessor_flags['cxx'].extend(
                modules.get_toolchain_flags())
            # Tell the compiler that C/C++ sources compiled in this rule are
            # part of the same module as the headers (and so have access to
            # private headers).
            if out_module:
                module_name = modules.get_module_name('fbcode', base_path, name)
                out_lang_preprocessor_flags['cxx'].append(
                    '-fmodule-name=' + module_name)
        if out_lang_preprocessor_flags:
            attributes['lang_preprocessor_flags'] = out_lang_preprocessor_flags

        # Form platform-specific processor flags.
        out_platform_preprocessor_flags = []
        out_platform_preprocessor_flags.extend(
            self.get_platform_flags_from_arch_flags(arch_preprocessor_flags))
        if out_platform_preprocessor_flags:
            attributes['platform_preprocessor_flags'] = (
                out_platform_preprocessor_flags)

        if lib_name is not None:
            attributes['soname'] = 'lib{}.so'.format(lib_name)

        exported_pp_flags = []
        self.verify_preprocessor_flags(
            'propagated_pp_flags',
            propagated_pp_flags)
        exported_pp_flags.extend(propagated_pp_flags)
        for path in (system_include_paths or []):
            exported_pp_flags.append('-isystem')
            exported_pp_flags.append(path)
        if exported_pp_flags:
            attributes['exported_preprocessor_flags'] = exported_pp_flags

        # Add in the base ldflags.
        out_ldflags.extend(
            self.get_ldflags(
                base_path,
                name,
                self.get_fbconfig_rule_type(),
                binary=self.is_binary(dlopen_info),
                deployable=self.is_deployable(),
                # Never apply stripping flags to library rules, as they only
                # get linked in `dev` mode which we avoid stripping in anyway,
                # any adding unused linker flags affects rule keys up the tree.
                strip_mode=None if self.is_deployable() else 'none',
                build_info=self.is_deployable(),
                lto=enable_lto,
                platform=platform if self.is_deployable() else None))

        # Add non-binary sanitizer dependencies.
        if (not self.is_binary(dlopen_info) and
                sanitizers.get_sanitizer() is not None):
            dependencies.extend(self.get_sanitizer_non_binary_deps())

        if self.is_binary(dlopen_info):
            if sanitizers.get_sanitizer() is not None:
                out_ldflags.extend(self.get_sanitizer_binary_ldflags())
            out_ldflags.extend(self.get_coverage_ldflags(base_path))
            if (self._context.buck_ops.read_config('fbcode', 'gdb-index') and
                  not core_tools.is_core_tool(base_path, name)):
                out_ldflags.append('-Wl,--gdb-index')
            ld_threads = self._context.buck_ops.read_config('fbcode', 'ld-threads')
            # lld does not (yet?) support the --thread-count option, so prevent
            # it from being forwarded when using lld.  bfd seems to be in the
            # same boat, and this happens on aarch64 machines.
            # FIXME: -fuse-ld= may take a path to an lld executable, for which
            #        this check will not work properly. Instead, maybe Context
            #        should have a member named 'linker', as it does with
            #        'compiler'?
            if ld_threads and \
               not core_tools.is_core_tool(base_path, name) and \
               '-fuse-ld=lld' not in out_ldflags and \
               platform_utils.get_platform_architecture(self.get_platform(base_path)) \
               != 'aarch64' and \
               '-fuse-ld=bfd' not in out_ldflags:
                out_ldflags.extend([
                    '-Wl,--threads',
                    '-Wl,--thread-count,' + ld_threads,
                ])

        if nodefaultlibs:
            out_ldflags.append('-nodefaultlibs')

        if emails or owner is not None:
            attributes['contacts'] = (
                self.convert_contacts(owner=owner, emails=emails))

        if env:
            attributes['env'] = self.convert_env_with_macros(base_path, env)

        if args:
            attributes['args'] = self.convert_args_with_macros(base_path, args)

        # Handle `dlopen_enabled` binaries.
        if dlopen_info is not None:

            # We don't support allocators with dlopen-enabled binaries.
            if allocator is not None:
                raise ValueError(
                    'Cannot use "allocator" parameter with dlopen enabled '
                    'binaries')

            # We're building a shared lib.
            out_ldflags.append('-shared')

            # If an explicit soname was specified, pass that in.
            soname = dlopen_info.get('soname')
            if soname is not None:
                out_ldflags.append('-Wl,-soname=' + soname)

            # Lastly, since we're building a shared lib, use the `static_pic`
            # link style so that PIC is used throughout.
            if out_link_style == 'static':
                out_link_style = 'static_pic'

        # Add in user-specified linker flags.
        if self.is_library():
            self.verify_linker_flags(linker_flags)
        for flag in linker_flags:
            macro_handlers = {}
            if self.is_binary(dlopen_info):
                macro_handlers['platform'] = (
                    lambda: platform_utils.get_buck_platform_for_base_path(base_path))
            if flag != '--enable-new-dtags':
                out_exported_ldflags.extend(
                    ['-Xlinker',
                     self.convert_blob_with_macros(
                         base_path,
                         flag,
                         extra_handlers=macro_handlers)])

        # Link non-link-whole libs with `--no-as-needed` to avoid adding
        # unnecessary DT_NEEDED tags during dynamic linking.  Libs marked
        # with `link_whole=True` may contain static intializers, and so
        # need to always generate a DT_NEEDED tag up the transitive link
        # tree. Ignore these arugments on OSX, as the linker doesn't support
        # them
        if (self.get_buck_rule_type() == 'cxx_library' and
                self._context.mode.startswith('dev') and
                plat.system() == 'Linux'):
            if link_whole is True:
                out_exported_ldflags.append('-Wl,--no-as-needed')
            else:
                out_exported_ldflags.append('-Wl,--as-needed')

        # Generate rules to handle lex sources.
        lex_srcs, srcs = self.split_matching_extensions_and_other(
            srcs, self.LEX_EXTS)
        for lex_src in lex_srcs:
            header, source, rules = (
                self.convert_lex(name, lex_args, lex_src, platform, visibility))
            out_headers.append(header)
            out_srcs.append(base.SourceWithFlags(RootRuleTarget(base_path, source[1:]), ['-w']))
            extra_rules.extend(rules)

        # Generate rules to handle yacc sources.
        yacc_srcs, srcs = self.split_matching_extensions_and_other(
            srcs, self.YACC_EXTS)
        for yacc_src in yacc_srcs:
            yacc_headers, source, rules = (
                self.convert_yacc(
                    base_path,
                    name,
                    yacc_args,
                    yacc_src,
                    platform,
                    visibility))
            out_headers.extend(yacc_headers)
            out_srcs.append(base.SourceWithFlags(RootRuleTarget(base_path, source[1:]), None))
            extra_rules.extend(rules)

        # Convert and add in any explicitly mentioned headers into our output
        # headers.
        if base.is_collection(headers):
            out_headers.extend(
                self.convert_source_list(base_path, headers))
        elif isinstance(headers, dict):
            headers_iter = headers.iteritems()
            converted = {
                k: self.convert_source(base_path, v) for k, v in headers_iter}

            if base.is_collection(out_headers):
                out_headers = {k: k for k in out_headers}

            out_headers.update(converted)

        # x in automatically inferred headers.
        auto_headers = (
            self.get_auto_headers(
                headers,
                auto_headers,
                self._context.buck_ops.read_config))
        if auto_headers == AutoHeaders.SOURCES:
            src_headers = set(self.get_headers_from_sources(base_path, srcs))
            src_headers -= set(out_headers)
            if isinstance(out_headers, list):
                out_headers.extend(sorted(src_headers))
            else:
                # Let it throw AttributeError if update() can't be found neither
                out_headers.update({k: k for k in src_headers})

        # Convert the `srcs` parameter.  If `known_warnings` is set, add in
        # flags to mute errors.
        for src in srcs:
            src = self.parse_source(base_path, src)
            flags = None
            if (known_warnings is True or
                    (known_warnings and
                     self.get_parsed_src_name(src) in known_warnings)):
                flags = ['-Wno-error']
            out_srcs.append(base.SourceWithFlags(src, flags))

        formatted_srcs = self.format_source_with_flags_list(out_srcs)
        if self.get_fbconfig_rule_type() != 'cpp_precompiled_header':
            attributes['srcs'], attributes['platform_srcs'] = formatted_srcs
        else:
            attributes['srcs'] = self.without_platforms(formatted_srcs)

        for lib in (shared_system_deps or []):
            out_exported_ldflags.append('-l' + lib)

        # We don't support symbols splitting, but we can at least strip the
        # debug symbols entirely (as some builds rely on the actual binary not
        # being bloated with debug info).
        if split_symbols:
            out_ldflags.append('-Wl,-S')

        # Handle DLL deps.
        if dlls:
            buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
            dll_rules, dll_deps, dll_ldflags, dll_dep_queries = (
                convert_dlls(base_path, name, platform, buck_platform, dlls,
                             self.get_fbcode_dir_from_gen_dir(), visibility))
            extra_rules.extend(dll_rules)
            dependencies.extend(dll_deps)
            out_ldflags.extend(dll_ldflags)
            if not dont_link_prerequisites:
                out_dep_queries.extend(dll_dep_queries)

            # We don't currently support dynamic linking with DLL support, as
            # we don't have a great way to prevent dependency DSOs needed by
            # the DLL, but *not* needed by the top-level binary, from being
            # dropped from the `DT_NEEDED` tags when linking with
            # `--as-needed`.
            if out_link_style == 'shared':
                out_link_style = 'static_pic'

        # Some libraries need to opt-out of linker errors about undefined
        # symbols.
        if (self.is_library() and
                # TODO(T23121628): The way we build shared libs in non-ASAN
                # sanitizer modes leaves undefined references to *SAN symbols.
                (sanitizers.get_sanitizer() is None or
                 sanitizers.get_sanitizer().startswith('address')) and
                # TODO(T23121628): Building python binaries with omnibus causes
                # undefined references in preloaded libraries, so detect this
                # via the link-style and ignore for now.
                self._context.link_style == 'shared' and
                not undefined_symbols):
            out_ldflags.append('-Wl,--no-undefined')

        # Get any linker flags for the current OS
        for os_short_name, flags in os_linker_flags:
            if os_short_name == self._context.config.get_current_os():
                out_exported_ldflags.extend(flags)

        # Set the linker flags parameters.
        if self.get_buck_rule_type() == 'cxx_library':
            attributes['exported_linker_flags'] = out_exported_ldflags
            attributes['linker_flags'] = out_ldflags
        else:
            attributes['linker_flags'] = out_exported_ldflags + out_ldflags

        attributes['labels'] = list(tags)

        if self.is_test(self.get_buck_rule_type()):
            attributes['labels'].extend(label_utils.convert_labels(platform, 'c++'))
            if self.is_coverage_enabled(base_path):
                attributes['labels'].append('coverage')
            attributes['use_default_test_main'] = use_default_test_main
            if 'serialize' in tags:
                attributes['run_test_separately'] = True

            # C/C++ gtest tests implicitly depend on gtest/gmock libs, and by
            # default on our custom main
            if type == 'gtest':
                gtest_deps = [
                    d.strip()
                    for d in re.split(
                        ",", self._context.config.get_gtest_lib_dependencies())
                ]
                if use_default_test_main:
                    gtest_deps.append(
                        self._context.config.get_gtest_main_dependency())
                dependencies.extend(
                    [target.parse_target(dep) for dep in gtest_deps])
            else:
                attributes['framework'] = type

        allocator = self.get_allocator(allocator)

        # C/C++ Lua main modules get statically linked into a special extension
        # module.
        if self.get_fbconfig_rule_type() == 'cpp_lua_main_module':
            attributes['preferred_linkage'] = 'static'

        # For binaries, set the link style.
        if self.is_buck_binary():
            attributes['link_style'] = out_link_style

        # Translate runtime files into resources.
        if runtime_files:
            attributes['resources'] = runtime_files

        # Translate additional coverage targets.
        if additional_coverage_targets:
            attributes['additional_coverage_targets'] = additional_coverage_targets

        # Convert three things here:
        # - Translate dependencies.
        # - Add and translate py3 sensitive deps
        # -  Grab OS specific dependencies and add them to the normal
        #    list of dependencies. We bypass buck's platform support because it
        #    requires us to parse a bunch of extra files we know we won't use,
        #    and because it's just a little fragile
        for dep in itertools.chain(
                deps,
                py3_sensitive_deps,
                *[
                    dep
                    for os, dep in os_deps
                    if os == self._context.config.get_current_os()
                ]):
            dependencies.append(target.parse_target(dep, base_path))

        # If we include any lex sources, implicitly add a dep on the lex lib.
        if lex_srcs:
            dependencies.append(LEX_LIB)

        # Add in binary-specific link deps.
        if self.is_binary(dlopen_info):
            d, r = self.get_binary_link_deps(
                base_path,
                name,
                attributes['linker_flags'],
                default_deps=not nodefaultlibs,
                allocator=allocator,
            )
            dependencies.extend(d)
            extra_rules.extend(r)

        if self.get_fbconfig_rule_type() == 'cpp_python_extension':
            dependencies.append(ThirdPartyRuleTarget('python', 'python'))
            # Generate an empty typing_config
            extra_rules.append(self.gen_typing_config(name, visibility=visibility))

        # Lua main module rules depend on are custom lua main.
        if self.get_fbconfig_rule_type() == 'cpp_lua_main_module':
            dependencies.append(
                RootRuleTarget('tools/make_lar', 'lua_main_decl'))
            dependencies.append(ThirdPartyRuleTarget('LuaJIT', 'luajit'))

            # When `embed_deps` is set, auto-dep deps on to the embed restore
            # libraries, which will automatically restore special env vars used
            # for loading the binary.
            if embed_deps:
                dependencies.append(RootRuleTarget('common/embed', 'lua'))
                dependencies.append(RootRuleTarget('common/embed', 'python'))

        # All Node extensions get the node headers.
        if self.get_fbconfig_rule_type() == 'cpp_node_extension':
            dependencies.append(
                ThirdPartyRuleTarget('node', 'node-headers'))

        # Add external deps.
        for dep in external_deps:
            dependencies.append(self.normalize_external_dep(dep))

        # Add in any CUDA deps.  We only add this if it's not always present,
        # it's common to explicitly depend on the cuda runtime.
        if cuda and not self.has_cuda_dep(dependencies):
            print('Warning: rule {}:{} with .cu files has to specify CUDA '
                  'external_dep to work.'.format(base_path, name))

        # Set the build platform, via both the `default_platform` parameter and
        # the default flavors support.
        if self.get_fbconfig_rule_type() != 'cpp_precompiled_header':
            buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
            attributes['default_platform'] = buck_platform
            if not self.is_deployable():
                attributes['defaults'] = {'platform': buck_platform}

        # Add in implicit deps.
        if not nodefaultlibs:
            dependencies.extend(self.get_implicit_deps())

        # Add implicit toolchain module deps.
        if modules.enabled():
            dependencies.extend(
                map(target.parse_target, modules.get_implicit_module_deps()))

        # Modularize libraries.
        if modules.enabled() and self.is_library() and out_module:

            # If we're using modules, we need to add in the `module.modulemap`
            # file and make sure it gets installed at the root of the include
            # tree so that clang can locate it for auto-loading.  To do this,
            # we need to clear the header namespace (which defaults to the base
            # path) and instead propagate its value via the keys of the header
            # dict so that we can make sure it's only applied to the user-
            # provided headers and not the module map.
            if base.is_collection(out_headers):
                out_headers = {paths.join(out_header_namespace, self.get_source_name(h)): h
                               for h in out_headers}
            else:
                out_headers = {paths.join(out_header_namespace, h): s
                               for h, s in out_headers.items()}
            out_header_namespace = ""

            # Create rule to generate the implicit `module.modulemap`.
            module_name = modules.get_module_name('fbcode', base_path, name)
            mmap_name = name + '-module-map'
            modules.module_map_rule(
                mmap_name,
                module_name,
                # There are a few header suffixes (e.g. '-inl.h') that indicate a
                # "private" extension to some library interface. We generally want
                # to keep these are non modular. So mark them private/textual.
                {h: ['private', 'textual']
                 if h.endswith(('-inl.h', '-impl.h', '-pre.h', '-post.h'))
                 else []
                 for h in out_headers})

            # Add in module map.
            out_headers["module.modulemap"] = ":" + mmap_name

            # Create module compilation rule.
            mod_name = name + '-module'
            module_flags = []
            module_flags.extend(out_preprocessor_flags)
            module_flags.extend(out_lang_preprocessor_flags['cxx'])
            module_flags.extend(exported_lang_pp_flags['cxx'])
            module_flags.extend(exported_pp_flags)
            module_platform_flags = []
            module_platform_flags.extend(out_platform_preprocessor_flags)
            module_platform_flags.extend(
                out_lang_plat_compiler_flags['cxx_cpp_output'])
            module_platform_flags.extend(out_platform_compiler_flags)
            module_deps, module_platform_deps = (
                self.format_all_deps(dependencies))
            modules.gen_module(
                mod_name,
                module_name,
                headers=out_headers,
                flags=module_flags,
                platform_flags=module_platform_flags,
                deps=module_deps,
                platform_deps=module_platform_deps,
            )

            # Expose module via C++ preprocessor flags.
            exported_lang_pp_flags['cxx'].append(
                '-fmodule-file={}=$(location :{})'
                .format(module_name, mod_name))

        # Write out our output headers.
        if out_headers:
            if self.get_buck_rule_type() == 'cxx_library':
                attributes['exported_headers'] = out_headers
            else:
                attributes['headers'] = out_headers

        # Set an explicit header namespace if not the default.
        if out_header_namespace != base_path:
            attributes['header_namespace'] = out_header_namespace

        if exported_lang_pp_flags:
            attributes['exported_lang_preprocessor_flags'] = exported_lang_pp_flags

        # If any deps were specified, add them to the output attrs.  For
        # libraries, we always use make these exported, since this is the
        # expected behavior in fbcode.
        if dependencies:
            deps_param, plat_deps_param = (
                ('exported_deps', 'exported_platform_deps')
                if self.is_library()
                else ('deps', 'platform_deps'))
            out_deps, out_plat_deps = self.format_all_deps(dependencies)
            attributes[deps_param] = out_deps
            if out_plat_deps:
                attributes[plat_deps_param] = out_plat_deps

        if out_dep_queries:
            attributes['deps_query'] = ' union '.join(out_dep_queries)
            attributes['link_deps_query_whole'] = True

        # fbconfig supports a `cpp_benchmark` rule which we convert to a
        # `cxx_binary`.  Just make sure we strip options that `cxx_binary`
        # doesn't support.
        if self.get_buck_rule_type() == 'cxx_binary':
            attributes.pop('args', None)
            attributes.pop('contacts', None)

        # (cpp|cxx)_precompiled_header rules take a 'src' attribute (not
        # 'srcs', drop that one which was stored above).  Requires a deps list.
        if self.get_buck_rule_type() == 'cxx_precompiled_header':
            attributes['src'] = src
            exclude_names = [
                'lang_platform_compiler_flags',
                'lang_preprocessor_flags',
                'linker_flags',
                'preprocessor_flags',
                'srcs',
            ]
            for exclude_name in exclude_names:
                if exclude_name in attributes:
                    attributes.pop(exclude_name)
            if 'deps' not in attributes:
                attributes['deps'] = []

        # Should we use a default PCH for this C++ lib / binary?
        # Only applies to certain rule types.
        if self._rule_type in (
                'cpp_library', 'cpp_binary', 'cpp_unittest',
                'cxx_library', 'cxx_binary', 'cxx_test'):
            # Was completely left out in the rule? (vs. None to disable autoPCH)
            if precompiled_header is ABSENT:
                precompiled_header = \
                    self.get_fbcode_default_pch(out_srcs, base_path, name)

        if precompiled_header:
            attributes['precompiled_header'] = precompiled_header

        if self.is_binary(dlopen_info) and versions is not None:
            attributes['version_universe'] = (
                self.get_version_universe(versions.items()))

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules

    def get_fbcode_default_pch(self, out_srcs, base_path, name):
        """
        Determine a default precompiled_header rule to use in this build.
        Return `None` if no default PCH configured / applicable to this rule.
        """
        # Don't mess with core tools + deps (mainly to keep rule keys stable).
        if self.exclude_from_auto_pch(base_path, name):
            return None
        # No sources to compile?  Then no point in precompiling.
        if not out_srcs:
            return None
        # Don't allow this to be used for anything non-C++.
        cpp_src_count = len([s for s in out_srcs if self.is_cpp_source(str(s))])
        if cpp_src_count != len(out_srcs):
            return None
        # Return the default PCH setting from config (`None` if absent).
        ret = self._context.buck_ops.read_config('fbcode', 'default_pch', None)
        # Literally the word 'None'?  This is to support disabling via command
        # line or in a .buckconfig from e.g. a unit test (see lua_cpp_main.py).
        if ret == "None":
            ret = None
        return ret

    def exclude_from_auto_pch(self, base_path, name):
        """
        Some cxx_library rules should not get PCHs auto-added; for the most
        part this is for core tools and their dependencies, so we don't
        change their rule keys.
        """
        if core_tools.is_core_tool(base_path, name):
            return True
        path = base_path.split('//', 1)[-1]

        if not path:
            return True
        path += '/'

        # t13036847 -- These are distilled from lists of dependencies for
        # things listed as core tools.  Instead of listing out every possible
        # specific dep here, I did exclude some directories pretty broadly,
        # to make maintaining this list simpler, and decrease the chance that
        # some other new core tool ends up picking a new dep not on this list.
        # Try this command to find stuff to add to this list:
        # buck query 'deps(%s, 1000)' \
        #   '//admarket/libadmarket/if:libadmarket_enum_map_gen' \
        #   '//dsi/logger/cpp/compiler:logger_cpp_gen' \
        #   ...  | sort -u
        # See tools/build/buck/config.py for CORE_TOOLS list.
        for pattern in self._context.config.get_auto_pch_blacklist():
            if path.startswith(pattern):
                return True

        # No reason to disable auto-PCH, that we know of.
        return False

    def convert_java_extension(
            self,
            base_path,
            name,
            dlopen_enabled=None,
            lib_name=None,
            visibility=None,
            **kwargs):
        """
        Convert a C/C++ Java extension.
        """

        rules = []

        # If we're not building in `dev` mode, then build extensions as
        # monolithic statically linked C/C++ shared libs.  We do this by
        # overriding some parameters to generate the extension as a dlopen-
        # enabled C/C++ binary, which also requires us generating the rule
        # under a different name, so we can use the user-facing name to
        # wrap the C/C++ binary in a prebuilt C/C++ library.
        if not self._context.mode.startswith('dev'):
            real_name = name
            name = name + '-extension'
            soname = (
                'lib{}.so'.format(
                    lib_name or
                    os.path.join(base_path, name).replace(os.sep, '_')))
            dlopen_enabled = {'soname': soname}
            lib_name = None

        # Delegate to the main conversion function, using potentially altered
        # parameters from above.
        rules.extend(
            self.convert_rule(
                base_path,
                name,
                dlopen_enabled=dlopen_enabled,
                lib_name=lib_name,
                visibility=visibility,
                **kwargs))

        # If we're building the monolithic extension, then setup additional
        # rules to wrap the extension in a prebuilt C/C++ library consumable
        # by Java dependents.
        if not self._context.mode.startswith('dev'):

            # Wrap the extension in a `prebuilt_cxx_library` rule
            # using the user-facing name.  This is what Java library
            # dependents will depend on.
            attrs = collections.OrderedDict()
            attrs['name'] = real_name
            if visibility is not None:
                attrs['visibility'] = visibility
            attrs['soname'] = soname
            platform = platform_utils.get_buck_platform_for_base_path(base_path)
            attrs['shared_lib'] = ':{}#{}'.format(name, platform)
            rules.append(Rule('prebuilt_cxx_library', attrs))

        return rules

    def convert_node_extension(
            self,
            base_path,
            name,
            dlopen_enabled=None,
            visibility=None,
            **kwargs):
        """
        Convert a C/C++ Java extension.
        """

        rules = []

        # Delegate to the main conversion function, making sure that we build
        # the extension into a statically linked monolithic DSO.
        rules.extend(
            self.convert_rule(
                base_path,
                name + '-extension',
                dlopen_enabled=True,
                visibility=visibility,
                **kwargs))
        rules[0].attributes['link_style'] = 'static_pic'

        # This is a bit weird, but `prebuilt_cxx_library` rules can only
        # accepted generated libraries that reside in a directory.  So use
        # a genrule to copy the library into a lib dir using it's soname.
        dest = os.path.join('node_modules', name, name + '.node')
        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = name + '-modules'
        attrs['cmd'] = ' && '.join([
            'mkdir -p $OUT/{}'.format(os.path.dirname(dest)),
            'cp $(location :{}-extension) $OUT/{}'.format(name, dest),
        ])
        rules.append(Rule('genrule', attrs))

        return rules

    def get_allowed_args(self):
        """
        Return the allowed arguments for this rule.
        """

        # Arguments that apply to all C/C++ rules.
        args = {
            'arch_compiler_flags',
            'arch_preprocessor_flags',
            'auto_headers',
            'compiler_flags',
            'compiler_specific_flags',
            'compile_with_modules',
            'deps',
            'external_deps',
            'global_symbols',
            'header_namespace',
            'headers',
            'known_warnings',
            'lex_args',
            'linker_flags',
            'name',
            'nodefaultlibs',
            'nvcc_flags',
            'precompiled_header',
            'preprocessor_flags',
            'py3_sensitive_deps',
            'shared_system_deps',
            'srcs',
            'supports_coverage',
            'system_include_paths',
            'visibility',
            'yacc_args',
            'additional_coverage_targets',
            'autodeps_keep',
            'tags',
        }

        # Set rule-type-specific args.
        rtype = self.get_fbconfig_rule_type()

        if rtype in ('cpp_benchmark', 'cpp_unittest'):
            args.update([
                'args',
                'emails',
                'env',
                'owner',
                'runtime_files',
                'tags',
            ])

        if rtype == 'cpp_unittest':
            args.update([
                'type',
                'use_default_test_main',
            ])

        if rtype == 'cpp_binary':
            args.update([
                'dlopen_enabled',
                'dont_link_prerequisites',
                'enable_lto',
                'hs_profile',
                'split_symbols',
                'os_deps',
                'os_linker_flags',
            ])

        if rtype in ('cpp_benchmark', 'cpp_binary', 'cpp_unittest'):
            args.update([
                'allocator',
                'dlls',
                'versions',
            ])

        if rtype == 'cpp_library':
            args.update([
                'lib_name',
                'link_whole',
                'module',
                'os_deps',
                'os_linker_flags',
                'preferred_linkage',
                'propagated_pp_flags',
                'undefined_symbols',
            ])

        if rtype == 'cpp_precompiled_header':
            args.update([
                'src',
            ])

        if rtype == 'cpp_python_extension':
            args.update([
                'base_module',
                # Intentionally not visible to users!
                #'module_name',
            ])

        if rtype == 'cpp_lua_extension':
            args.update([
                'base_module',
            ])

        if rtype == 'cpp_java_extension':
            args.update([
                'lib_name',
            ])

        if rtype == 'cpp_lua_main_module':
            args.update([
                'embed_deps',
            ])

        return args

    def convert(self, base_path, name, visibility=None, **kwargs):
        """
        Entry point for converting C/C++ rules.
        """

        rules = []

        rtype = self.get_fbconfig_rule_type()
        if rtype == 'cpp_java_extension':
            rules.extend(
                self.convert_java_extension(base_path, name, visibility=visibility, **kwargs))
        elif rtype == 'cpp_node_extension':
            rules.extend(
                self.convert_node_extension(base_path, name, visibility=visibility, **kwargs))
        else:
            rules.extend(
                self.convert_rule(base_path, name, visibility=visibility, **kwargs))

        return rules
