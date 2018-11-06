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
import re

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/cxx_sources.py".format(macro_root), "cxx_sources")
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:auto_pch_blacklist.bzl", "auto_pch_blacklist")
load("@fbcode_macros//build_defs:lex.bzl", "lex", "LEX_EXTS", "LEX_LIB")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:cuda.bzl", "cuda")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:modules.bzl", module_utils="modules")
load("@fbcode_macros//build_defs:auto_headers.bzl", "AutoHeaders", "get_auto_headers")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:build_mode.bzl", _build_mode="build_mode")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:yacc.bzl", "yacc", "YACC_EXTS")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:haskell_common.bzl", "haskell_common")

load("@bazel_skylib//lib:partial.bzl", "partial")


def _cuda_compiler_specific_flags_partial(compiler_specific_flags, has_cuda_srcs, _, compiler):
    return compiler_specific_flags.get("gcc" if has_cuda_srcs else compiler)

"""
A marker which helps us differentiate between empty/falsey/None values
defaulted in a function's arg list, vs. actually passed in from the caller
with such a value.
"""
ABSENT = tuple()


class CppConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(CppConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

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
            base, ext = paths.split_extension(src)
            if ext in exts:
                matches.append(src)
            else:
                leftovers.append(src)

        return (matches, leftovers)

    def get_headers_from_sources(self, base_path, srcs):
        """
        Return the headers likely associated with the given sources.
        """

        source_exts = cpp_common.SOURCE_EXTS  # use a local for faster lookups in a loop
        # Check for // in case this src is a rule
        split_srcs = (
            paths.split_extension(src)
            for src in srcs
            if '//' not in src and not src.startswith(':'))

        headers = native.glob([
            base + hext
            for base, ext in split_srcs if ext in source_exts
            for hext in cxx_sources.HEADER_SUFFIXES])
        return headers

    def get_sanitizer_binary_ldflags(self):
        """
        Return any linker flags to use when linking binaries with sanitizer
        support.
        """

        sanitizer = sanitizers.get_sanitizer()
        assert sanitizer != None

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
        assert sanitizer != None

        deps = []

        # We link ASAN weak stub symbols into every DSO so that we don't leave
        # undefined references to *SAN symbols at shared library link time,
        # which allows us to pass `--no-undefined` to the linker to prevent
        # undefined symbols.
        if (sanitizer.startswith('address') and
                self.get_link_style() == 'shared'):
            deps.append(target_utils.RootRuleTarget('tools/build/sanitizers', 'asan-stubs'))

        return deps

    def get_lua_base_module_parts(self, base_path, base_module):
        """
        Get the list of base module parts for this rule.
        """

        # If base module is unset, prepare a default.
        if base_module == None:
            return ['fbcode'] + base_path.split('/')

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

    def parse_modules_val(self, val, source, base_path, name):
        """
        Parse a config value used to enabled/disable modules.
        """

        if val is None:
            return None

        # First, try parse as an fixed point probability against the hash of
#this rule's name.
        try:
            prob = int(val)
        except ValueError:
            pass
        else:
            if not (prob >= 0 and prob <= 100):
                raise ValueError(
                    '`{}` probability must be between'
                    ' 0 and 100: {!r}'.format(source, prob))
# Weak attempt at consistent hashing
            val = 0
            for c in (base_path + ':' + name):
                val += ord(c) ^ val
            val = val % 100
            return prob > val

        # Otherwise, parse as a boolean.
        if val.lower() == 'true':
            return True
        elif val.lower() == 'false':
            return False
        else:
            raise TypeError(
                '`{}`: cannot coerce {!r} to bool'
                .format(source, val))

    def read_modules_default(self, base_path, name):
        return self.parse_modules_val(
            self._context.buck_ops.read_config('cxx', 'modules_default'),
            'cxx.modules_default',
            base_path,
            name)

    def convert_rule(
            self,
            base_path,
            name,
            buck_rule_type,
            is_library,
            is_buck_binary,
            is_test,
            is_deployable,
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
            modular_headers=None,
            modules=None,
            overridden_link_style=None):

        visibility = get_visibility(visibility, name)

        if not isinstance(compiler_flags, (list, tuple)):
            fail(
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
        build_mode = _build_mode.get_build_mode_for_base_path(base_path)
        dlopen_info = cpp_common.normalize_dlopen_enabled(dlopen_enabled)
        # `dlopen_enabled=True` binaries are really libraries.
        is_binary = False if dlopen_info != None else is_deployable
        exported_lang_pp_flags = collections.defaultdict(list)
        platform = (
            platform_utils.get_platform_for_base_path(
                base_path
                if self.get_fbconfig_rule_type() != 'cpp_node_extension'
                # Node rules always use the platforms set in the root PLATFORM
                # file.
                else ''))

        has_cuda_srcs = cuda.has_cuda_srcs(srcs)

        # TODO(lucian, pbrady, T24109997): this was a temp hack when CUDA doesn't
        # support platform007
        # We still keep it here in case CUDA is lagging on gcc support again;
        # For projects that don't really need CUDA, but depend on CUDA through
        # convenience transitive dependencies, we exclude the CUDA files to
        # unblock migration. Once CUDA supports gcc of the new platform,
        # cuda_deps should be merged back into deps.
        if platform.startswith('platform008'):
            has_cuda_srcs = False

            def filter_flags(flags):
                banned_flags = [
                    "-DUSE_CUDNN=1",
                    "-DUSE_CUDNN",
                    "-DCAFFE2_USE_CUDNN",
                    "-DUSE_CUDA",
                    "-DUSE_CUDA_FUSER_FBCODE=1",
                ]
                return [f for f in flags if f not in banned_flags]

            def filter_flags_dict(flags_dict):
                if flags_dict == None:
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

            # These targets we keep (for headers, flags etc), but drop all their cpp files wholesale.
            banned_cuda_targets = {
                "caffe2/aten:ATen-cu",
                "caffe2/caffe2:caffe2_cu",
                "caffe2/caffe2:caffe2_gpu",
                "caffe2/torch/lib/c10d:c10d",
                "caffe2/torch/lib/THD:THD",
                "gloo:gloo-cuda",
            }
            if "{}:{}".format(base_path, name) in banned_cuda_targets:
                print('Warning: no CUDA on platform007: rule {}:{} ignoring all srcs: {}'
                      .format(base_path, name, srcs))
                srcs = []

            # More granular cpp blacklist.
            banned_cuda_srcs_re = [re.compile(pattern) for pattern in [
                "caffe2/caffe2/.*cudnn.cc",
                "caffe2/caffe2/.*gpu.cc",
                "caffe2/caffe2/contrib/nervana/.*gpu.cc",
                "caffe2/caffe2/operators/.*cudnn.cc",
                "caffe2/caffe2/fb/operators/scale_gradient_op_gpu.cc",
                "caffe2/caffe2/fb/predictor/PooledPredictor.cpp",
                "caffe2/caffe2/fb/predictor/PredictorGPU.cpp",
                "caffe2/:generate-code=THCUNN.cpp",
                "caffe2/torch/csrc/jit/fusers/cuda/.*.cpp",
                "caffe2/torch/csrc/cuda/.*.cpp",
                "caffe2/torch/csrc/distributed/c10d/ddp.cpp"
            ]]

            def is_banned_src(src):
                return any(r.match(src) for r in banned_cuda_srcs_re)

            cuda_srcs = [s for s in srcs if cuda.is_cuda_src(s) or is_banned_src(base_path + '/' + s)]
            srcs = [s for s in srcs if s not in cuda_srcs]
            if cuda_srcs:
                print('Warning: no CUDA on platform007: rule {}:{} ignoring cuda_srcs: {}'
                      .format(base_path, name, cuda_srcs))

        # Figure out whether this rule's headers should be built into a clang
        # module (in supporting build modes).
        out_modular_headers = True
        # Check the global, build mode default.
        global_modular_headers = (
            self.read_bool('cxx', 'modular_headers_default', required=False))
        if global_modular_headers != None:
            out_modular_headers = global_modular_headers
        # Check the build mode file override.
        if (build_mode != None and
                build_mode.cxx_modular_headers != None):
            out_modular_headers = build_mode.cxx_modular_headers
        # Check the rule override.
        if modular_headers != None:
            out_modular_headers = modular_headers

        # Figure out whether this rule should be built using clang modules (in
        # supporting build modes).
        out_modules = True
        # Check the global, build mode default.
        global_modules = self.read_modules_default(base_path, name)
        if global_modules != None:
            out_modules = global_modules
        # Check the build mode file override.
        if build_mode != None and build_mode.cxx_modules != None:
            out_modules = build_mode.cxx_modules
        # Check the rule override.
        if modules != None:
            out_modules = modules
        # Don't build precompiled headers with modules.
        if self.get_fbconfig_rule_type() == 'cpp_precompiled_header':
            out_modules = False
        if precompiled_header != ABSENT:
            out_modules = False

        attributes = collections.OrderedDict()

        attributes['name'] = name

        if visibility != None:
            attributes['visibility'] = visibility

        # Set the base module.
        rule_type = self.get_fbconfig_rule_type()
        if rule_type == 'cpp_lua_extension':
            attributes['base_module'] = (
                self.get_lua_base_module(base_path, base_module))
        elif rule_type == 'cpp_python_extension' and base_module != None:
            attributes['base_module'] = base_module

        if module_name != None:
            attributes['module_name'] = module_name

        if is_library:
            if preferred_linkage:
                attributes['preferred_linkage'] = preferred_linkage
            if link_whole:
                attributes['link_whole'] = link_whole
            if global_symbols:
                if platform_utils.get_platform_architecture(
                        platform_utils.get_platform_for_base_path(base_path)) == 'aarch64':
                    # On aarch64 we use bfd linker which doesn't support
                    # --export-dynamic-symbol. We force link_whole instead.
                    attributes['link_whole'] = True
                else:
                    flag = ('undefined' if out_link_style == 'static' else
                            'export-dynamic-symbol')
                    out_exported_ldflags = ['-Wl,--%s,%s' % (flag, sym)
                                            for sym in global_symbols]

        # Parse the `header_namespace` parameter.
        if header_namespace != None:
            header_namespace_whitelist = config.get_header_namespace_whitelist()
            if (base_path, name) not in header_namespace_whitelist and not any(
                # Check base path prefix in header_namespace_whitelist
                len(t) == 1 and base_path.startswith(t[0])
                for t in header_namespace_whitelist
            ):
                fail(
                    '{}(): the `header_namespace` parameter is *not* '
                    'supported in fbcode -- `#include` paths must match '
                    'their fbcode-relative path. ({}/{})'
                    .format(self.get_fbconfig_rule_type(), base_path, name))
            out_header_namespace = header_namespace
        else:
            out_header_namespace = base_path

        # Form compiler flags.  We pass everything as language-specific flags
        # so that we can can control the ordering.
        out_lang_plat_compiler_flags = cpp_flags.get_compiler_flags(base_path)
        for lang in cpp_flags.COMPILER_LANGS:
            out_lang_plat_compiler_flags.setdefault(lang, [])
            out_lang_plat_compiler_flags[lang].extend(
                src_and_dep_helpers.format_platform_param(compiler_flags))
            out_lang_plat_compiler_flags[lang].extend(
                src_and_dep_helpers.format_platform_param(
                    partial.make(
                        _cuda_compiler_specific_flags_partial,
                        compiler_specific_flags,
                        has_cuda_srcs)))

        out_lang_plat_compiler_flags.setdefault('cuda_cpp_output', [])
        out_lang_plat_compiler_flags['cuda_cpp_output'].extend(
            src_and_dep_helpers.format_platform_param(
                list(itertools.chain(
                    *[('-_NVCC_', flag) for flag in nvcc_flags]))))

        clang_profile = native.read_config('cxx', 'profile')
        if clang_profile != None:
            compiler.require_global_compiler(
                "cxx.profile only supported by modes using clang globally",
                "clang")
            profile_args = [
                '-fprofile-sample-use=$(location {})'.format(clang_profile),
                '-fdebug-info-for-profiling',
                # '-fprofile-sample-accurate'
            ]
            out_lang_plat_compiler_flags['c_cpp_output'].extend(
                src_and_dep_helpers.format_platform_param(profile_args))
            out_lang_plat_compiler_flags['cxx_cpp_output'].extend(
                src_and_dep_helpers.format_platform_param(profile_args))

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
        if not has_cuda_srcs:
            if sanitizers.get_sanitizer() != None:
                out_preprocessor_flags.extend(sanitizers.get_sanitizer_flags())
            out_preprocessor_flags.extend(coverage.get_coverage_flags(base_path))
        cpp_common.assert_preprocessor_flags(
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
        if build_mode != None:
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
            cpp_flags.get_extra_cppflags())
        out_lang_preprocessor_flags['cxx'].extend(
            cpp_flags.get_extra_cxxppflags())
        out_lang_preprocessor_flags['assembler_with_cpp'].extend(
            cpp_flags.get_extra_cxxppflags())
        if module_utils.enabled() and out_modules:
            # Add module toolchain flags.
            out_lang_preprocessor_flags['cxx'].extend(
                module_utils.get_toolchain_flags())
            # Tell the compiler that C/C++ sources compiled in this rule are
            # part of the same module as the headers (and so have access to
            # private headers).
            if out_modular_headers:
                module_name = (
                    module_utils.get_module_name('fbcode', base_path, name))
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

        if lib_name != None:
            attributes['soname'] = 'lib{}.so'.format(lib_name)

        exported_pp_flags = []
        cpp_common.assert_preprocessor_flags(
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
                binary=is_binary,
                deployable=is_deployable,
                # Never apply stripping flags to library rules, as they only
                # get linked in `dev` mode which we avoid stripping in anyway,
                # any adding unused linker flags affects rule keys up the tree.
                strip_mode=None if is_deployable else 'none',
                build_info=is_deployable,
                lto=enable_lto,
                platform=platform if is_deployable else None))

        # Add non-binary sanitizer dependencies.
        if (not is_binary and
                sanitizers.get_sanitizer() != None):
            dependencies.extend(self.get_sanitizer_non_binary_deps())

        if is_binary:
            if sanitizers.get_sanitizer() != None:
                out_ldflags.extend(self.get_sanitizer_binary_ldflags())
            out_ldflags.extend(coverage.get_coverage_ldflags(base_path))
            if (native.read_config('fbcode', 'gdb-index') and
                  not core_tools.is_core_tool(base_path, name)):
                out_ldflags.append('-Wl,--gdb-index')
            ld_threads = native.read_config('fbcode', 'ld-threads')
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
               platform_utils.get_platform_architecture(platform_utils.get_platform_for_base_path(base_path)) \
               != 'aarch64' and \
               '-fuse-ld=bfd' not in out_ldflags:
                out_ldflags.extend([
                    '-Wl,--threads',
                    '-Wl,--thread-count,' + ld_threads,
                ])

        if nodefaultlibs:
            out_ldflags.append('-nodefaultlibs')

        if emails or owner != None:
            attributes['contacts'] = (
                self.convert_contacts(owner=owner, emails=emails))

        if env:
            attributes['env'] = self.convert_env_with_macros(base_path, env)

        if args:
            attributes['args'] = self.convert_args_with_macros(base_path, args)

        # Handle `dlopen_enabled` binaries.
        if dlopen_info != None:

            # We don't support allocators with dlopen-enabled binaries.
            if allocator != None:
                fail(
                    'Cannot use "allocator" parameter with dlopen enabled '
                    'binaries')

            # We're building a shared lib.
            out_ldflags.append('-shared')

            # If an explicit soname was specified, pass that in.
            soname = dlopen_info.get('soname')
            if soname != None:
                out_ldflags.append('-Wl,-soname=' + soname)

            # Lastly, since we're building a shared lib, use the `static_pic`
            # link style so that PIC is used throughout.
            if out_link_style == 'static':
                out_link_style = 'static_pic'

        # Add in user-specified linker flags.
        if is_library:
            cpp_common.assert_linker_flags(linker_flags)

        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        for flag in linker_flags:
            macro_handlers = {}
            if flag != '--enable-new-dtags':
                linker_text = self.convert_blob_with_macros(base_path, flag)
                if is_binary:
                    linker_text = linker_text.replace("$(platform)", buck_platform)
                out_exported_ldflags.extend(['-Xlinker', linker_text])

        # Link non-link-whole libs with `--no-as-needed` to avoid adding
        # unnecessary DT_NEEDED tags during dynamic linking.  Libs marked
        # with `link_whole=True` may contain static intializers, and so
        # need to always generate a DT_NEEDED tag up the transitive link
        # tree. Ignore these arugments on OSX, as the linker doesn't support
        # them
        if (buck_rule_type == 'cxx_library' and
                config.get_build_mode().startswith('dev') and
                native.host_info().os.is_linux):
            if link_whole is True:
                out_exported_ldflags.append('-Wl,--no-as-needed')
            else:
                out_exported_ldflags.append('-Wl,--as-needed')

        # Generate rules to handle lex sources.
        lex_srcs, srcs = self.split_matching_extensions_and_other(srcs, LEX_EXTS)
        for lex_src in lex_srcs:
            header, source = lex(name, lex_args, lex_src, platform, visibility)
            out_headers.append(header)
            out_srcs.append(cpp_common.SourceWithFlags(target_utils.RootRuleTarget(base_path, source[1:]), ['-w']))

        # Generate rules to handle yacc sources.
        yacc_srcs, srcs = self.split_matching_extensions_and_other(
            srcs, YACC_EXTS)
        for yacc_src in yacc_srcs:
            yacc_headers, source = yacc(
                name,
                yacc_args,
                yacc_src,
                platform,
                visibility)
            out_headers.extend(yacc_headers)
            out_srcs.append(cpp_common.SourceWithFlags(target_utils.RootRuleTarget(base_path, source[1:]), None))

        # Convert and add in any explicitly mentioned headers into our output
        # headers.
        if base.is_collection(headers):
            out_headers.extend(
                src_and_dep_helpers.convert_source_list(base_path, headers))
        elif isinstance(headers, dict):
            headers_iter = headers.iteritems()
            converted = {
                k: src_and_dep_helpers.convert_source(base_path, v) for k, v in headers_iter}

            if base.is_collection(out_headers):
                out_headers = {k: k for k in out_headers}

            out_headers.update(converted)

        # x in automatically inferred headers.
        auto_headers = get_auto_headers(auto_headers)
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
            src = src_and_dep_helpers.parse_source(base_path, src)
            flags = None
            if (known_warnings is True or
                    (known_warnings and
                     self.get_parsed_src_name(src) in known_warnings)):
                flags = ['-Wno-error']
            out_srcs.append(cpp_common.SourceWithFlags(src, flags))

        formatted_srcs = cpp_common.format_source_with_flags_list(out_srcs)
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
            dll_deps, dll_ldflags, dll_dep_queries = (
                haskell_common.convert_dlls(
                    name, platform, buck_platform, dlls, visibility))
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
        if (is_library and
                # TODO(T23121628): The way we build shared libs in non-ASAN
                # sanitizer modes leaves undefined references to *SAN symbols.
                (sanitizers.get_sanitizer() == None or
                 sanitizers.get_sanitizer().startswith('address')) and
                # TODO(T23121628): Building python binaries with omnibus causes
                # undefined references in preloaded libraries, so detect this
                # via the link-style and ignore for now.
                config.get_default_link_style() == 'shared' and
                not undefined_symbols):
            out_ldflags.append('-Wl,--no-undefined')

        # Get any linker flags for the current OS
        for os_short_name, flags in os_linker_flags:
            if os_short_name == config.get_current_os():
                out_exported_ldflags.extend(flags)

        # Set the linker flags parameters.
        if buck_rule_type == 'cxx_library':
            attributes['exported_linker_flags'] = out_exported_ldflags
            attributes['linker_flags'] = out_ldflags
        else:
            attributes['linker_flags'] = out_exported_ldflags + out_ldflags

        attributes['labels'] = list(tags)

        if is_test:
            attributes['labels'].extend(label_utils.convert_labels(platform, 'c++'))
            if coverage.is_coverage_enabled(base_path):
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
                        ",", config.get_gtest_lib_dependencies())
                ]
                if use_default_test_main:
                    gtest_deps.append(
                        config.get_gtest_main_dependency())
                dependencies.extend(
                    [target_utils.parse_target(dep) for dep in gtest_deps])
            else:
                attributes['framework'] = type

        allocator = allocators.normalize_allocator(allocator)

        # C/C++ Lua main modules get statically linked into a special extension
        # module.
        if self.get_fbconfig_rule_type() == 'cpp_lua_main_module':
            attributes['preferred_linkage'] = 'static'

        # For binaries, set the link style.
        if is_buck_binary:
            attributes['link_style'] = overridden_link_style or out_link_style

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
                    if os == config.get_current_os()
                ]):
            dependencies.append(target_utils.parse_target(dep, default_base_path=base_path))

        # If we include any lex sources, implicitly add a dep on the lex lib.
        if lex_srcs:
            dependencies.append(LEX_LIB)

        # Add in binary-specific link deps.
        if is_binary:
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
            dependencies.append(target_utils.ThirdPartyRuleTarget('python', 'python'))
            # Generate an empty typing_config
            extra_rules.append(self.gen_typing_config(name, visibility=visibility))

        # Lua main module rules depend on are custom lua main.
        if self.get_fbconfig_rule_type() == 'cpp_lua_main_module':
            dependencies.append(
                target_utils.RootRuleTarget('tools/make_lar', 'lua_main_decl'))
            dependencies.append(target_utils.ThirdPartyRuleTarget('LuaJIT', 'luajit'))

            # When `embed_deps` is set, auto-dep deps on to the embed restore
            # libraries, which will automatically restore special env vars used
            # for loading the binary.
            if embed_deps:
                dependencies.append(target_utils.RootRuleTarget('common/embed', 'lua'))
                dependencies.append(target_utils.RootRuleTarget('common/embed', 'python'))

        # All Node extensions get the node headers.
        if self.get_fbconfig_rule_type() == 'cpp_node_extension':
            dependencies.append(
                target_utils.ThirdPartyRuleTarget('node', 'node-headers'))

        # Add external deps.
        for dep in external_deps:
            dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

        # Add in any CUDA deps.  We only add this if it's not always present,
        # it's common to explicitly depend on the cuda runtime.
        if has_cuda_srcs and not cuda.has_cuda_dep(dependencies):
            # TODO: If this won't work, should it just fail?
            print('Warning: rule {}:{} with .cu files has to specify CUDA '
                  'external_dep to work.'.format(base_path, name))

        # Set the build platform, via both the `default_platform` parameter and
        # the default flavors support.
        if self.get_fbconfig_rule_type() != 'cpp_precompiled_header':
            buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
            attributes['default_platform'] = buck_platform
            if not is_deployable:
                attributes['defaults'] = {'platform': buck_platform}

        # Add in implicit deps.
        if not nodefaultlibs:
            dependencies.extend(
                cpp_common.get_implicit_deps(
                    self.get_fbconfig_rule_type() == 'cpp_precompiled_header'))

        # Add implicit toolchain module deps.
        if module_utils.enabled() and out_modules:
            dependencies.extend(
                map(target_utils.parse_target, module_utils.get_implicit_module_deps()))

        # Modularize libraries.
        if module_utils.enabled() and is_library and out_modular_headers:

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
            module_name = module_utils.get_module_name('fbcode', base_path, name)
            mmap_name = name + '-module-map'
            module_utils.module_map_rule(
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
                src_and_dep_helpers.format_all_deps(dependencies))
            module_utils.gen_module(
                mod_name,
                module_name,
                # TODO(T32915747): Due to a clang bug when using module and
                # header maps together, clang cannot update the module at load
                # time with the correct path to it's new home location (modules
                # are originally built in the sandbox of a Buck `genrule`, but
                # are used from a different location: Buck's header symlink
                # trees.  To work around this, we add support for manually
                # fixing up the embedded module home location to be the header
                # symlink tree.
                override_module_home=(
                    'buck-out/{}/gen/{}/{}#header-mode-symlink-tree-with-header-map,headers%s'
                    .format(config.get_build_mode(), base_path, name)),
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
            if buck_rule_type == 'cxx_library':
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
                if is_library
                else ('deps', 'platform_deps'))
            out_deps, out_plat_deps = src_and_dep_helpers.format_all_deps(dependencies)
            attributes[deps_param] = out_deps
            if out_plat_deps:
                attributes[plat_deps_param] = out_plat_deps

        if out_dep_queries:
            attributes['deps_query'] = ' union '.join(out_dep_queries)
            attributes['link_deps_query_whole'] = True

        # fbconfig supports a `cpp_benchmark` rule which we convert to a
        # `cxx_binary`.  Just make sure we strip options that `cxx_binary`
        # doesn't support.
        if buck_rule_type == 'cxx_binary':
            attributes.pop('args', None)
            attributes.pop('contacts', None)

        # (cpp|cxx)_precompiled_header rules take a 'src' attribute (not
        # 'srcs', drop that one which was stored above).  Requires a deps list.
        if buck_rule_type == 'cxx_precompiled_header':
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
            if precompiled_header == ABSENT:
                precompiled_header = cpp_common.get_fbcode_default_pch(out_srcs, base_path, name)

        if precompiled_header:
            attributes['precompiled_header'] = precompiled_header

        if is_binary and versions != None:
            attributes['version_universe'] = (
                self.get_version_universe(versions.items()))

        return [Rule(buck_rule_type, attributes)] + extra_rules


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
            'deps',
            'external_deps',
            'global_symbols',
            'header_namespace',
            'headers',
            'known_warnings',
            'lex_args',
            'linker_flags',
            'modules',
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
                'modular_headers',
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
        rtype = self.get_fbconfig_rule_type()
        if rtype == 'cpp_java_extension':
            # This logic is contained in the CppJavaExtensionConverter
            fail("cpp_java_extension called incorrectly")
        elif rtype == 'cpp_node_extension':
            # This logic is contained in the CppNodeExtensionConverter
            fail("cpp_node_extension called incorrectly")
        return self.convert_rule(base_path, name, visibility=visibility, **kwargs)


# TODO: These are temporary until all logic is extracted into cpp_common
class CppLibraryConverter(CppConverter):
    def __init__(self, context):
        super(CppLibraryConverter, self).__init__(context, 'cpp_library')

    def convert(self, *args, **kwargs):
        return super(CppLibraryConverter, self).convert(
            buck_rule_type = 'cxx_library',
            is_library = True,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )

class CppBinaryConverter(CppConverter):
    def __init__(self, context):
        super(CppBinaryConverter, self).__init__(context, 'cpp_binary')

    def convert(self, *args, **kwargs):
        return super(CppBinaryConverter, self).convert(
            buck_rule_type = 'cxx_binary',
            is_library = False,
            is_buck_binary = True,
            is_test = False,
            is_deployable = True,
            *args,
            **kwargs
        )

class CppUnittestConverter(CppConverter):
    def __init__(self, context):
        super(CppUnittestConverter, self).__init__(context, 'cpp_unittest')

    def convert(self, *args, **kwargs):
        return super(CppUnittestConverter, self).convert(
            buck_rule_type = 'cxx_test',
            is_library = False,
            is_buck_binary = True,
            is_test = True,
            is_deployable = True,
            *args,
            **kwargs
        )

class CppBenchmarkConverter(CppConverter):
    def __init__(self, context):
        super(CppBenchmarkConverter, self).__init__(context, 'cpp_benchmark')

    def convert(self, *args, **kwargs):
        return super(CppBenchmarkConverter, self).convert(
            buck_rule_type = 'cxx_binary',
            is_library = False,
            is_buck_binary = True,
            is_test = False,
            is_deployable = True,
            *args,
            **kwargs
        )

class CppNodeExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppNodeExtensionConverter, self).__init__(context, 'cpp_node_extension')

    def convert(
            self,
            base_path,
            name,
            dlopen_enabled=None,
            visibility=None,
            **kwargs):

        # Delegate to the main conversion function, making sure that we build
        # the extension into a statically linked monolithic DSO.
        rules = self.convert_rule(
            base_path,
            name + '-extension',
            buck_rule_type = 'cxx_binary',
            is_library = False,
            is_buck_binary = True,
            is_test = False,
            is_deployable = False,
            dlopen_enabled=True,
            visibility=visibility,
            overridden_link_style = 'static_pic',
            **kwargs
        )

        # This is a bit weird, but `prebuilt_cxx_library` rules can only
        # accepted generated libraries that reside in a directory.  So use
        # a genrule to copy the library into a lib dir using it's soname.
        dest = paths.join('node_modules', name, name + '.node')
        native.genrule(
            name = name,
            visibility = visibility,
            out = name + "-modules",
            cmd = ' && '.join([
                'mkdir -p $OUT/{}'.format(paths.dirname(dest)),
                'cp $(location :{}-extension) $OUT/{}'.format(name, dest),
            ]),
        )

        return rules

class CppPrecompiledHeaderConverter(CppConverter):
    def __init__(self, context):
        super(CppPrecompiledHeaderConverter, self).__init__(context, 'cpp_precompiled_header')

    def convert(self, *args, **kwargs):
        return super(CppPrecompiledHeaderConverter, self).convert(
            buck_rule_type = 'cxx_precompiled_header',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )

class CppPythonExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppPythonExtensionConverter, self).__init__(context, 'cpp_python_extension')

    def convert(self, *args, **kwargs):
        return super(CppPythonExtensionConverter, self).convert(
            buck_rule_type = 'cxx_python_extension',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )

class CppJavaExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppJavaExtensionConverter, self).__init__(context, 'cpp_java_extension')

    def convert(
            self,
            base_path,
            name,
            visibility=None,
            lib_name=None,
            dlopen_enabled=None,
            *args,
            **kwargs):

        rules = []

        # If we're not building in `dev` mode, then build extensions as
        # monolithic statically linked C/C++ shared libs.  We do this by
        # overriding some parameters to generate the extension as a dlopen-
        # enabled C/C++ binary, which also requires us generating the rule
        # under a different name, so we can use the user-facing name to
        # wrap the C/C++ binary in a prebuilt C/C++ library.
        if not config.get_build_mode().startswith('dev'):
            real_name = name
            name = name + '-extension'
            soname = (
                'lib{}.so'.format(
                    lib_name or
                    paths.join(base_path, name).replace('/', '_')))
            dlopen_enabled = {'soname': soname}
            lib_name = None

        # Delegate to the main conversion function, using potentially altered
        # parameters from above.
        rules.extend(
            super(CppJavaExtensionConverter, self).convert_rule(
                base_path,
                name,
                buck_rule_type = 'cxx_library' if config.get_build_mode().startswith("dev") else 'cxx_binary',
                is_library = False,
                is_buck_binary = False,
                is_test = False,
                is_deployable = False,
                dlopen_enabled=dlopen_enabled,
                lib_name=lib_name,
                visibility=visibility,
                **kwargs))

        # If we're building the monolithic extension, then setup additional
        # rules to wrap the extension in a prebuilt C/C++ library consumable
        # by Java dependents.
        if not config.get_build_mode().startswith('dev'):

            # Wrap the extension in a `prebuilt_cxx_library` rule
            # using the user-facing name.  This is what Java library
            # dependents will depend on.
            platform = platform_utils.get_buck_platform_for_base_path(base_path)
            native.prebuilt_cxx_library(
                name = real_name,
                visibility = visibility,
                soname = soname,
                shared_lib = ':{}#{}'.format(name, platform),
            )

        return rules

class CppLuaExtensionConverter(CppConverter):
    def __init__(self, context):
        super(CppLuaExtensionConverter, self).__init__(context, 'cpp_lua_extension')

    def convert(self, *args, **kwargs):
        return super(CppLuaExtensionConverter, self).convert(
            buck_rule_type = 'cxx_lua_extension',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )

class CppLuaMainModuleConverter(CppConverter):
    def __init__(self, context):
        super(CppLuaMainModuleConverter, self).__init__(context, 'cpp_lua_main_module')

    def convert(self, *args, **kwargs):
        return super(CppLuaMainModuleConverter, self).convert(
            buck_rule_type = 'cxx_library',
            is_library = False,
            is_buck_binary = False,
            is_test = False,
            is_deployable = False,
            *args,
            **kwargs
        )
