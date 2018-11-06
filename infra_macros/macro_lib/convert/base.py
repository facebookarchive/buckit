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
import copy
import functools
import json
import pipes
import re

with allow_unsafe_import():
    from distutils.version import LooseVersion
    import os
    import platform as platmod
    import shlex
    import textwrap


# Hack to make include_defs flake8 safe.
_include_defs = include_defs  # noqa: F821


# Hack to make include_defs sane and less magical forr flake8
def include_defs(path):
    global _include_defs__imported
    _include_defs(path, '_include_defs__imported')  # noqa: F821
    ret = _include_defs__imported
    del _include_defs__imported
    return ret


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    return include_defs('{}/{}.py'.format(
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ))


Rule = import_macro_lib('rule').Rule
target = import_macro_lib('target')
build_info = import_macro_lib('build_info')
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:build_mode.bzl", _build_mode="build_mode")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:modules.bzl", "modules")
load("@fbcode_macros//build_defs:python_typing.bzl", "gen_typing_config_attrs")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_flags")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/facebook:python_wheel_overrides.bzl", "python_wheel_overrides")

load("@bazel_skylib//lib:partial.bzl", "partial")

MACRO_PATTERN = (
    re.compile('\\$\\((?P<name>[^)\\s]+)(?: (?P<args>[^)]*))?\\)'))


Context = collections.namedtuple(
    'Context',
    [
        'buck_ops',
        'build_mode',
        'default_compiler',
        'global_compiler',
        'coverage',
        'link_style',
        'mode',
        'lto_type',
        'third_party_config',
        'config',
    ],
)


BuckOperations = collections.namedtuple(
    'BuckOperations',
    [
        'add_build_file_dep',
        'glob',
        'include_defs',
        'read_config',
    ],
)


Tp2ProjectBuild = collections.namedtuple(
    'Tp2ProjectBuild',
    [
        'project_deps',
        'subdir',
        'versions',
    ],
)


CXX_BUILD_INFO_TEMPLATE = """\
#include <stdint.h>

const char* const BuildInfo_kBuildMode = "{build_mode}";
const char* const BuildInfo_kBuildTool = "{build_tool}";
const char* const BuildInfo_kCompiler = "{compiler}";
const char* const BuildInfo_kHost = "{host}";
const char* const BuildInfo_kPackageName = "{package_name}";
const char* const BuildInfo_kPackageVersion = "{package_version}";
const char* const BuildInfo_kPackageRelease = "{package_release}";
const char* const BuildInfo_kPath = "{path}";
const char* const BuildInfo_kPlatform = "{platform}";
const char* const BuildInfo_kRevision = "{revision}";
const char* const BuildInfo_kRule = "{rule}";
const char* const BuildInfo_kRuleType = "{rule_type}";
const char* const BuildInfo_kTime = "{time}";
const char* const BuildInfo_kTimeISO8601 = "{time_iso8601}";
const char* const BuildInfo_kUpstreamRevision = "{upstream_revision}";
const char* const BuildInfo_kUser = "{user}";
const uint64_t BuildInfo_kRevisionCommitTimeUnix = {revision_epochtime};
const uint64_t BuildInfo_kTimeUnix = {epochtime};
const uint64_t BuildInfo_kUpstreamRevisionCommitTimeUnix =
  {upstream_revision_epochtime};
"""

GENERATED_LIB_SUFFIX = '__generated-lib__'


def is_collection(obj):
    """
    Return whether the object is a array-like collection.
    """

    for typ in (list, set, tuple):
        if isinstance(obj, typ):
            return True

    return False

_THIN_LTO_FLAG = ["-flto=thin"]
_LTO_FLAG = ["-flto"]

def _lto_linker_flags_partial(_, compiler):
    if compiler != "clang":
        return []
    if config.get_lto_type() == "thin":
        return _THIN_LTO_FLAG
    return _LTO_FLAG

class Converter(object):

    def __init__(self, context):
        self._context = context
        self._tp2_build_dat_cache = {}

    def get_third_party_root(self, platform):
        if self._context.config.get_third_party_use_platform_subdir():
            return os.path.join(
                self._context.config.get_third_party_buck_directory(),
                platform)
        else:
            return self._context.config.get_third_party_buck_directory()

    def get_third_party_build_root(self, platform):
        if self._context.config.get_third_party_use_build_subdir():
            return os.path.join(self.get_third_party_root(platform), 'build')
        else:
            return self.get_third_party_root(platform)

    def get_third_party_tools_root(self, platform):
        return os.path.join(self.get_third_party_root(platform), 'tools')

    def get_platform_flags_from_arch_flags(self, arch_flags):
        """
        Format a dict of architecture names to flags into a platform flag list
        for Buck.
        """

        def _get_platform_flags_from_arch_flags_partial(platform_flags, platform, _):
            return platform_flags.get(platform)


        platform_flags = {}
        for arch, flags in sorted(arch_flags.items()):
            platforms = platform_utils.get_platforms_for_architecture(arch)
            for platform in platform_utils.get_platforms_for_architecture(arch):
                platform_flags[platform] = flags

        return src_and_dep_helpers.format_platform_param(
            partial.make(
                _get_platform_flags_from_arch_flags_partial, platform_flags))

    def get_tool_version(self, platform, project):
        conf = self._context.third_party_config['platforms'][platform]
        return LooseVersion(conf['tools']['projects'][project])

    def get_tool_target(self, target, platform):
        """
        Return the target for the tool described by the given RuleTarget.
        """

        return target_utils.to_label(
            None,
            third_party.get_tool_path(target.base_path, platform),
            target.name)

    def get_tp2_dep_path(self, project, platform):
        """
        Return the path within third-party for the given project. This will be
        the directory, not a specific target or binary. Based on configuration,
        and the path may be modified to fit fbcode's layout
        """

        if self._context.config.get_third_party_use_build_subdir():
            return os.path.join(self.get_third_party_root(platform), 'build', project)
        else:
            return project

    def without_platforms(self, formatted):  # type: PlatformParam[Any, List[Tuple[str, Any]]] -> Any
        """
        Drop platform-specific component of the fiven `PlatformParam`, erroring
        out if it contained anything.
        """

        param, platform_param = formatted
        if platform_param:
            raise ValueError(
                'unexpected platform sources: {!r}'.format(platform_param))

        return param

    def convert_blob_with_macros(
            self,
            base_path,
            blob,
            platform=None):
        """
        Convert build targets inside macros.
        """
        return third_party.replace_third_party_repo(blob, platform=platform)

    def convert_args_with_macros(self, base_path, blobs, platform=None):
        return [self.convert_blob_with_macros(base_path, b, platform=platform)
                for b in blobs]

    def convert_env_with_macros(self, base_path, env, platform=None):
        new_env = {}
        for k, v in env.iteritems():
            new_env[k] = (
                self.convert_blob_with_macros(base_path, v, platform=platform))
        return new_env

    def merge_platform_deps(self, dst, src):
        for platform, deps in src.iteritems():
            dst.setdefault(platform, [])
            dst[platform].extend(deps)

    def is_test(self, buck_rule_type):
        return buck_rule_type.endswith('_test')

    def get_parsed_src_name(self, src):
        """
        Get the logical name of the given source.
        """

        # If this is a build target, extract the name from the `=<name>`
        # suffix.
        rule_name = getattr(src, "name", None)
        if rule_name != None:
            return src_and_dep_helpers.extract_source_name(rule_name)

        # Otherwise, the name is the source itself.
        else:
            return src

    def get_source_name(self, src):
        """
        Get the logical name of the given source.
        """

        # If this is a build target, extract the name from the `=<name>`
        # suffix.
        if src[0] in '/@:':
            return src_and_dep_helpers.extract_source_name(src)

        # Otherwise, the name is the source itself.
        else:
            return src

    def read_choice(self, section, field, choices, default=None):
        """
        Read a string from `.buckconfig` which can be one of the values given
        in `choices`.
        """

        val = self._context.buck_ops.read_config(section, field)
        if val is not None:
            if val in choices:
                return val
            else:
                raise TypeError(
                    '`{}:{}`: must be one of ({}), but was {!r}'
                    .format(section, field, ', '.join(choices), val))
        elif default is not None:
            return default
        else:
            raise KeyError(
                '`{}:{}`: no value set'.format(section, field))

    def read_bool(self, section, field, default=None, required=True):
        """
        Read a `boolean` from `.buckconfig`.
        """

        val = self._context.buck_ops.read_config(section, field)
        if val is not None:
            if val.lower() == 'true':
                return True
            elif val.lower() == 'false':
                return False
            else:
                raise TypeError(
                    '`{}:{}`: cannot coerce {!r} to bool'
                    .format(section, field, val))
        elif default is not None:
            return default
        elif required:
            raise KeyError(
                '`{}:{}`: no value set'.format(section, field))

    def read_int(self, section, field, default=None):
        """
        Read an `int` from `.buckconfig`.
        """

        val = self._context.buck_ops.read_config(section, field)
        if val is not None:
            try:
                return int(val)
            except ValueError as e:
                raise TypeError(
                    '`{}:{}`: cannot coerce {!r} to int: {}'
                    .format(section, field, val, e))
        elif default is not None:
            return default
        else:
            raise KeyError(
                '`{}:{}`: no value set'.format(section, field))

    def read_string(self, section, field, default=None):
        """
        Read a `string` from `.buckconfig`.
        """

        val = self._context.buck_ops.read_config(section, field)
        if val is None:
            val = default
        return val

    def read_list(self, section, field, default=None):
        """
        Read a `list` from `.buckconfig`.
        """

        val = self._context.buck_ops.read_config(section, field)
        if val is None:
            return default
        return val.split()

    def get_strip_mode(self, base_path, name):
        """
        Return a flag to strip debug symbols from binaries, or `None` if
        stripping is not enabled.
        """

        # `dev` mode has lightweight binaries, so avoid stripping to keep rule
        # keys stable.
        if self._context.mode.startswith('dev'):
            return 'none'

        # If this is a core tool, we never strip to keep stable rule keys.
        if core_tools.is_core_tool(base_path, name):
            return 'none'

        # Otherwise, read the config setting.
        return self.read_choice(
            'misc',
            'strip_binaries',
            ['none', 'debug-non-line', 'full'],
            default='none')

    def get_strip_ldflag(self, mode):
        """
        Return the linker flag to use for the given strip mode.
        """

        if mode == 'full':
            return '-Wl,-S'
        elif mode == 'debug-non-line':
            return '-Wl,--strip-debug-non-line'
        elif mode == 'none':
            return None
        else:
            raise Exception('invalid strip mode: ' + mode)

    def get_build_info_linker_flags(
            self,
            base_path,
            name,
            rule_type,
            platform,
            compiler):
        """
        Get the linker flags to configure how the linker embeds build info.
        """

        ldflags = []

        mode = build_info.get_build_info_mode(base_path, name)

        # Make sure we're not using non-deterministic build info when caching
        # is enabled.
        if mode == 'full' and self.read_bool('cxx', 'cache_links', True):
            raise ValueError(
                'cannot use `full` build info when `cxx.cache_links` is set')

        # Add in explicit build info args.
        if mode != 'none':
            # Pass the build info mode to the linker.
            ldflags.append('--build-info=' + mode)
            explicit = (
                build_info.get_explicit_build_info(
                    base_path,
                    name,
                    rule_type,
                    platform,
                    compiler))
            ldflags.append('--build-info-build-mode=' + explicit.build_mode)
            if explicit.package_name:
                ldflags.append(
                    '--build-info-package-name=' + explicit.package_name)
            if explicit.package_release:
                ldflags.append(
                    '--build-info-package-release=' + explicit.package_release)
            if explicit.package_version:
                ldflags.append(
                    '--build-info-package-version=' + explicit.package_version)
            ldflags.append('--build-info-compiler=' + explicit.compiler)
            ldflags.append('--build-info-platform=' + explicit.platform)
            ldflags.append('--build-info-rule=' + explicit.rule)
            ldflags.append('--build-info-rule-type=' + explicit.rule_type)

        return ldflags

    def read_shlib_interfaces(self, buck_platform):
        return self.read_choice(
            'cxx#' + buck_platform,
            'shlib_interfaces',
            ['disabled', 'enabled', 'defined_only'])

    def get_binary_ldflags(self, base_path, name, rule_type, platform):
        """
        Return ldflags set via various `.buckconfig` settings.
        """

        ldflags = []

        # If we're using TSAN, we need to build PIEs.
        if sanitizers.get_sanitizer() == 'thread':
            ldflags.append('-pie')

        # It's rare, but some libraries use variables defined in object files
        # in the top-level binary.  This works as, when linking the binary, the
        # linker sees this undefined reference in the dependent shared library
        # and so makes sure to export this symbol definition to the binary's
        # dynamic symbol table.  However, when using shared library interfaces
        # in `defined_only` mode, undefined references are stripped from shared
        # libraries, so the linker never knows to export these symbols to the
        # binary's dynamic symbol table, and the binary fails to load at
        # runtime, as the dynamic loader can't resolve that symbol.
        #
        # So, when linking a binary when using shared library interfaces in
        # `defined_only` mode, pass `--export-dynamic` to the linker to force
        # everything onto the dynamic symbol table.  Since this only affects
        # object files from sources immediately owned by `cpp_binary` rules,
        # this shouldn't have much of a performance issue.
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        if (cpp_common.get_link_style() == 'shared' and
                self.read_shlib_interfaces(buck_platform) == 'defined_only'):
            ldflags.append('-Wl,--export-dynamic')

        return ldflags

    def get_lto_level(self):
        """
        Returns the user-specific LTO parallelism level.
        """

        default = 32 if self._context.lto_type else 0
        return self.read_int('cxx', 'lto', default)

    def is_lto_enabled(self):
        """
        Returns whether to use LTO for this build.
        """

        return self.get_lto_level() > 0

    def get_gcc_lto_ldflags(self, base_path, platform):
        """
        Get linker flags required for gcc LTO.
        """

        flags = []

        # Verify we're running with a build mode that supports LTO.
        if self._context.lto_type != 'fat':
            raise ValueError('build mode doesn\'t support {} LTO'.format(
                self._context.lto_type))

        # Read the LTO parallelism level from the config, where `0` disables
        # LTO.
        lto_level = self.get_lto_level()
        assert lto_level > 0, lto_level

        # When linking with LTO, we need to pass compiler flags that affect
        # code generation back into the linker.  Since we don't actually
        # discern code generation flags from language specific flags, just
        # pass all our C/C++ compiler flags in.
        buck_platform = platform_utils.to_buck_platform(platform, 'gcc')
        compiler_flags = cpp_flags.get_compiler_flags(base_path)
        section = 'cxx#{}'.format(buck_platform)
        flags.extend(read_flags(section, 'cflags', []))
        for plat_re, cflags in compiler_flags['c_cpp_output']:
            if re.search(plat_re, buck_platform):
                flags.extend(cflags)
        flags.extend(read_flags(section, 'cxxflags', []))
        for plat_re, cflags in compiler_flags['cxx_cpp_output']:
            if re.search(plat_re, buck_platform):
                flags.extend(cflags)

        flags.extend([
            # Some warnings that only show up at lto time.
            '-Wno-free-nonheap-object',
            '-Wno-odr',
            '-Wno-lto-type-mismatch',

            # Set the linker that flags that will run LTO.
            '-fuse-linker-plugin',
            '-flto={}'.format(lto_level),
            '--param=lto-partitions={}'.format(lto_level * 2),
        ])

        return flags

    def get_ldflags(
            self,
            base_path,
            name,
            rule_type,
            binary=False,
            deployable=None,
            strip_mode=None,
            build_info=False,
            lto=False,
            platform=None):
        """
        Return linker flags to apply to links.
        """

        # Default `deployable` to whatever `binary` was set to, as very rule
        # types make a distinction.
        if deployable is None:
            deployable = binary

        # The `binary`, `build_info`, and `plaform` params only make sense for
        # "deployable" rules.
        assert not binary or deployable
        assert not lto or deployable
        assert not build_info or deployable
        assert not (deployable ^ (platform is not None))

        ldflags = []

        # 1. Add in build-mode ldflags.
        build_mode = _build_mode.get_build_mode_for_base_path(base_path)
        if build_mode is not None:
            ldflags.extend(build_mode.ld_flags)

        # 2. Add flag to strip debug symbols.
        if strip_mode is None:
            strip_mode = self.get_strip_mode(base_path, name)
        strip_ldflag = self.get_strip_ldflag(strip_mode)
        if strip_ldflag is not None:
            ldflags.append(strip_ldflag)

        # 3. Add in flags specific for linking a binary.
        if binary:
            ldflags.extend(
                self.get_binary_ldflags(base_path, name, rule_type, platform))

        # 4. Add in the build info linker flags.
        # In OSS, we don't need to actually use the build info (and the
        # linker will not understand these options anyways) so skip in that case
        if build_info and self._context.config.get_use_build_info_linker_flags():
            ldflags.extend(
                self.get_build_info_linker_flags(
                    base_path,
                    name,
                    rule_type,
                    platform,
                    compiler.get_compiler_for_current_buildfile()))

        # 5. If enabled, add in LTO linker flags.
        if self.is_lto_enabled():
            compiler.require_global_compiler(
                'can only use LTO in modes with a fixed global compiler')
            if self._context.global_compiler == 'clang':
                if self._context.lto_type not in ('monolithic', 'thin'):
                    raise ValueError(
                        'clang does not support {} LTO'
                        .format(self._context.lto_type))
                # Clang does not support fat LTO objects, so we build everything
                # as IR only, and must also link everything with -flto
                ldflags.append('-flto=thin' if self._context.lto_type ==
                               'thin' else '-flto')
                # HACK(marksan): don't break HFSort/"Hot Text" (t19644410)
                ldflags.append('-Wl,-plugin-opt,-function-sections')
                ldflags.append('-Wl,-plugin-opt,-profile-guided-section-prefix=false')
                # Equivalent of -fdebug-types-section for LLVM backend
                ldflags.append('-Wl,-plugin-opt,-generate-type-units')
            else:
                assert self._context.global_compiler == 'gcc'
                if self._context.lto_type != 'fat':
                    raise ValueError(
                        'gcc does not support {} LTO'
                        .format(cxx_mode.lto_type))
                # GCC has fat LTO objects, where we build everything as both IR
                # and object code and then conditionally opt-in here, at link-
                # time, based on "enable_lto" in the TARGETS file.
                if lto:
                    ldflags.extend(self.get_gcc_lto_ldflags(base_path, platform))
                else:
                    ldflags.append('-fno-lto')

        # 6. Add in command-line ldflags.
        ldflags.extend(cpp_flags.get_extra_ldflags())

        return ldflags

    def get_binary_link_deps(
            self,
            base_path,
            name,
            linker_flags=(),
            allocator='malloc',
            default_deps=True):
        """
        Return a list of dependencies that should apply to *all* binary rules
        that link C/C++ code.
        """

        deps = []
        rules = []

        # If we're not using a sanitizer add allocator deps.
        if sanitizers.get_sanitizer() is None:
            deps.extend(allocators.get_allocator_deps(allocator))

        # Add in any dependencies required for sanitizers.
        deps.extend(sanitizers.get_sanitizer_binary_deps())
        d, r = self.create_sanitizer_configuration(
            base_path,
            name,
            linker_flags,
        )
        deps.extend(d)
        rules.extend(r)

        # Add in any dependencies required for code coverage
        if coverage.get_coverage():
            deps.extend(coverage.get_coverage_binary_deps())

        # We link in our own implementation of `kill` to binaries (S110576).
        if default_deps:
            deps.append(target_utils.RootRuleTarget('common/init', 'kill'))

        return deps, rules

    def create_cxx_build_info_rule(
            self,
            base_path,
            name,
            rule_type,
            platform,
            linker_flags=(),
            static=True,
            visibility=None):
        """
        Create rules to generate a C/C++ library with build info.
        """

        rules = []

        # Setup a rule to generate the build info C file.
        source_name = name + '-cxx-build-info'
        info = CXX_BUILD_INFO_TEMPLATE.format(
            **self.get_build_info(
                base_path,
                name,
                rule_type,
                platform))
        source_attrs = collections.OrderedDict()
        source_attrs['name'] = source_name
        if visibility is not None:
            source_attrs['visibility'] = visibility
        source_attrs['out'] = source_name + '.c'
        source_attrs['cmd'] = (
            'mkdir -p `dirname $OUT` && echo {0} > $OUT'
            .format(pipes.quote(info)))
        rules.append(Rule('genrule', source_attrs))

        # Setup a rule to compile the build info C file into a library.
        lib_name = name + '-cxx-build-info-lib'
        lib_attrs = collections.OrderedDict()
        lib_attrs['name'] = lib_name
        if visibility is not None:
            lib_attrs['visibility'] = visibility
        lib_attrs['srcs'] = [':' + source_name]
        lib_attrs['compiler_flags'] = cpp_flags.get_extra_cflags()
        lib_attrs['linker_flags'] = (
            list(cpp_flags.get_extra_ldflags()) +
            ['-nodefaultlibs'] +
            list(linker_flags))

        # Setup platform default for compilation DB, and direct building.
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        lib_attrs['default_platform'] = buck_platform
        lib_attrs['defaults'] = {'platform': buck_platform}

        # Clang does not support fat LTO objects, so we build everything
        # as IR only, and must also link everything with -flto
        if self.is_lto_enabled():
            lib_attrs['platform_linker_flags'] = (
                src_and_dep_helpers.format_platform_param(
                    partial.make(_lto_linker_flags_partial)))

        if static:
            # Use link_whole to make sure the build info symbols are always
            # added to the binary, even if the binary does not refer to them.
            lib_attrs['link_whole'] = True
            # Use force_static so that the build info symbols are always put
            # directly in the main binary, even if dynamic linking is used.
            lib_attrs['force_static'] = True
        rules.append(Rule('cxx_library', lib_attrs))

        return target_utils.RootRuleTarget(base_path, lib_name), rules

    def get_build_info(self, base_path, name, rule_type, platform):
        if core_tools.is_core_tool(base_path, name):
            # Ignore user-provided build-info args for a set of core
            # targets and just return defaults (as if the user hadn't
            # provided built-info in the first place).
            def default_read_config(info, field, default):
                return default
            read_config = default_read_config
        else:
            read_config = self._context.buck_ops.read_config

        build_info = collections.OrderedDict()
        build_info['build_tool'] = 'buck'
        build_info['build_mode'] = self._context.mode
        build_info['compiler'] = compiler.get_compiler_for_current_buildfile()
        build_info['epochtime'] = (
            int(read_config('build_info', 'epochtime', '0')))
        build_info['host'] = read_config('build_info', 'host', '')
        build_info['package_name'] = (
            read_config('build_info', 'package_name', ''))
        build_info['package_version'] = (
            read_config('build_info', 'package_version', ''))
        build_info['package_release'] = (
            read_config('build_info', 'package_release', ''))
        build_info['path'] = read_config('build_info', 'path', '')
        build_info['platform'] = platform
        build_info['revision'] = read_config('build_info', 'revision', '')
        build_info['revision_epochtime'] = (
            int(read_config('build_info', 'revision_epochtime', '0')))
        build_info['rule'] = 'fbcode:' + base_path + ':' + name
        build_info['rule_type'] = rule_type
        build_info['time'] = read_config('build_info', 'time', '')
        build_info['time_iso8601'] = (
            read_config('build_info', 'time_iso8601', ''))
        build_info['upstream_revision'] = (
            read_config('build_info', 'upstream_revision', ''))
        build_info['upstream_revision_epochtime'] = (
            int(read_config('build_info', 'upstream_revision_epochtime', '0')))
        build_info['user'] = read_config('build_info', 'user', '')
        return build_info

    def create_sanitizer_configuration(
            self,
            base_path,
            name,
            linker_flags=()):
        """
        Create rules to generate a C/C++ library with sanitizer configuration
        """

        deps = []
        rules = []

        sanitizer = sanitizers.get_sanitizer()
        build_mode = _build_mode.get_build_mode_for_base_path(base_path)

        configuration_src = []

        sanitizer_variable_format = 'const char* const {name} = "{options}";'

        def gen_options_var(name, default_options, extra_options):
            if extra_options:
                options = default_options.copy()
                options.update(extra_options)
            else:
                options = default_options

            s = sanitizer_variable_format.format(
                name=name,
                options=':'.join([
                    '{}={}'.format(k, v)
                    for k, v in sorted(options.iteritems())
                ])
            )
            return s

        if sanitizer and sanitizer.startswith('address'):
            configuration_src.append(gen_options_var(
                'kAsanDefaultOptions',
                sanitizers.ASAN_DEFAULT_OPTIONS,
                build_mode.asan_options if build_mode else None,
            ))
            configuration_src.append(gen_options_var(
                'kUbsanDefaultOptions',
                sanitizers.UBSAN_DEFAULT_OPTIONS,
                build_mode.ubsan_options if build_mode else None,
            ))

            if build_mode and build_mode.lsan_suppressions:
                lsan_suppressions = build_mode.lsan_suppressions
            else:
                lsan_suppressions = sanitizers.LSAN_DEFAULT_SUPPRESSIONS
            configuration_src.append(
                sanitizer_variable_format.format(
                    name='kLSanDefaultSuppressions',
                    options='\\n'.join([
                        'leak:{}'.format(l) for l in lsan_suppressions
                    ])
                )
            )

        if sanitizer and sanitizer == 'thread':
            configuration_src.append(gen_options_var(
                'kTsanDefaultOptions',
                sanitizers.TSAN_DEFAULT_OPTIONS,
                build_mode.tsan_options if build_mode else None,
            ))

        lib_name = name + '-san-conf-' + GENERATED_LIB_SUFFIX
        # Setup a rule to generate the sanitizer configuration C file.
        source_gen_name = name + '-san-conf'
        source_attrs = collections.OrderedDict()
        source_attrs['name'] = source_gen_name
        source_attrs['visibility'] = [
            '//{base_path}:{lib_name}'
            .format(base_path=base_path, lib_name=lib_name)
        ]
        source_attrs['out'] = 'san-conf.c'
        source_attrs['cmd'] = (
            'mkdir -p `dirname $OUT` && echo {0} > $OUT'
            .format(pipes.quote('\n'.join(configuration_src))))
        rules.append(Rule('genrule', source_attrs))

        # Setup a rule to compile the sanitizer configuration C file
        # into a library.
        lib_attrs = collections.OrderedDict()
        lib_attrs['name'] = lib_name
        lib_attrs['visibility'] = [
            '//{base_path}:{name}'
            .format(base_path=base_path, name=name)
        ]
        lib_attrs['srcs'] = [':' + source_gen_name]
        lib_attrs['compiler_flags'] = cpp_flags.get_extra_cflags()

        # Setup platform default for compilation DB, and direct building.
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        lib_attrs['default_platform'] = buck_platform
        lib_attrs['defaults'] = {'platform': buck_platform}

        lib_linker_flags = []
        if linker_flags:
            lib_linker_flags = (
                list(cpp_flags.get_extra_ldflags()) +
                ['-nodefaultlibs'] +
                list(linker_flags)
            )
        if lib_linker_flags:
            lib_attrs['linker_flags'] = lib_linker_flags

        # Clang does not support fat LTO objects, so we build everything
        # as IR only, and must also link everything with -flto
        if self.is_lto_enabled():
            lib_attrs['platform_linker_flags'] = (
                src_and_dep_helpers.format_platform_param(
                    partial.make(_lto_linker_flags_partial)))


        # Use link_whole to make sure the build info symbols are always
        # added to the binary, even if the binary does not refer to them.
        lib_attrs['link_whole'] = True
        # Use force_static so that the build info symbols are always put
        # directly in the main binary, even if dynamic linking is used.
        lib_attrs['force_static'] = True

        rules.append(Rule('cxx_library', lib_attrs))
        deps.append(target_utils.RootRuleTarget(base_path, lib_name))

        return deps, rules

    def convert_contacts(self, owner=None, emails=None):
        """
        Convert the `owner` and `emails` parameters in Buck-style contacts.
        """

        contacts = []

        # `owner` is either a string or list.
        if owner is not None:
            if isinstance(owner, basestring):
                contacts.append(owner)
            else:
                contacts.extend(owner)

        if emails is not None:
            contacts.extend(emails)

        return contacts

    def get_buck_out_path(self):
        return self._context.buck_ops.read_config(
            'project',
            'buck_out',
            'buck-out')

    def get_gen_path(self):
        return os.path.join(
            self.get_buck_out_path(),
            'gen')

    def get_bin_path(self):
        return os.path.join(
            self.get_buck_out_path(),
            'bin')

    def get_fbcode_dir_from_gen_dir(self):
        return os.path.relpath(os.curdir, self.get_gen_path())

    def copy_rule(self, src, name, out=None, propagate_versions=False, visibility=None):
        """
        Returns a `genrule` which copies the given source.
        """

        if out is None:
            out = name

        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = out
        attrs['cmd'] = ' && '.join([
            'mkdir -p `dirname $OUT`',
            'cp {src} $OUT'.format(src=src),
        ])

        # If this rule needs to be part of the versioned sub-tree of it's
        # consumer, use a `cxx_genrule` which propagates versions (e.g. this
        # is useful for cases like `hsc2hs` which should use a dep tree which
        # is part of the same version sub-tree as the top-level binary).
        genrule_type = 'cxx_genrule' if propagate_versions else 'genrule'

        return Rule(genrule_type, attrs)

    def generate_merge_tree_rule(
            self,
            base_path,
            name,
            paths,
            deps,
            visibility=None):
        """
        Generate a rule which creates an output dir with the given paths merged
        with the merged directories of it's dependencies.
        """

        cmds = []

        for dep in sorted(deps):
            cmds.append('rsync -a $(location {})/ "$OUT"'.format(dep))
        for src in sorted(paths):
            src = self.get_source_name(src)
            dst = os.path.join('"$OUT"', base_path, src)
            cmds.append('mkdir -p {}'.format(os.path.dirname(dst)))
            cmds.append('cp {} {}'.format(src, dst))

        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = os.curdir
        attrs['srcs'] = sorted(paths)
        attrs['cmd'] = ' && '.join(cmds)
        return Rule('genrule', attrs)

    def get_tp2_build_dat(self, base_path):
        """
        Load the TP2 metadata for the TP2 project at the given base path.
        """

        build_dat = self._tp2_build_dat_cache.get(base_path)
        if build_dat is not None:
            return build_dat

        fbsource_root = read_config('fbsource', 'repo_relative_path', '..');
        build_dat_name = os.path.join(fbsource_root, "fbcode", base_path, 'build.dat')
        self._context.buck_ops.add_build_file_dep('fbcode//' + build_dat_name)
        with open(build_dat_name) as f:
            build_dat = json.load(f)

        self._tp2_build_dat_cache[base_path] = build_dat
        return build_dat

    def get_tp2_platform(self, base_path):
        """
        Get the fbcode this tp2 project was built for.
        """

        return self.get_tp2_build_dat(base_path)['platform']

    def get_tp2_project_builds(self, base_path, relevant_deps=None):
        """
        Return the implicit project deps and their corresponding versions for
        each build of the TP2 project at the given base path.
        """

        build_dat = self.get_tp2_build_dat(base_path)
        default_versions = (
            {p: v[0] for p, v in build_dat['dependencies'].items()})

        def should_skip_build(build_dep_versions):
            """
            Returns whether this project build should skipped, which happens
            when using non-default versions of irrelevant dependencies.
            """

            # If the user passed in an explicit relevant dep list, verify that
            # any deps this project build was against were either in the
            # relevant dep list or were using default versions.
            if relevant_deps is not None:
                for dep, version in build_dep_versions.items():
                    if (dep not in relevant_deps and
                            version != default_versions[dep]):
                        return True

            return False

        project_builds = collections.OrderedDict()

        for build, versions in sorted(build_dat['builds'].items()):

            # If this buils isnt usable, skip it.
            if should_skip_build(versions):
                continue

            build_deps = collections.OrderedDict()
            for project, version in sorted(versions.items()):

                # If this isn't a relevant, ignore it.
                if relevant_deps is not None and project not in relevant_deps:
                    continue

                pdep = (
                    target_utils.target_to_label(
                        third_party.get_tp2_project_target(project),
                        platform=build_dat['platform']))
                build_deps[pdep] = version

            project_builds[build] = (
                Tp2ProjectBuild(
                    project_deps=build_deps,
                    subdir=build,
                    versions=versions))

        # If we have just one build, `buckify_tp2` will inline its contents,
        # so update the returned dict to reflect this.
        if len(build_dat['builds']) == 1:
            (name, build), = project_builds.items()
            project_builds = {name: build._replace(subdir='')}

        # We should have at least one build.
        assert project_builds

        return project_builds

    def get_tp2_project_dep(self, base_path):
        """
        Return the self-referencing project dep to use for the TP2 project at
        the given base path, or `None` if this project doesn't have one.
        """

        project = base_path.split(os.sep)[3]
        platform = self.get_tp2_platform(base_path)
        return target_utils.target_to_label(
            third_party.get_tp2_project_target(project),
            platform=platform)

    def create_error_rules(self, name, msg, visibility=None):
        """
        Return rules which generate an error with the given message at build
        time.
        """

        rules = []

        msg = 'ERROR: {}'.format(msg)
        msg = os.linesep.join(textwrap.wrap(msg, 79, subsequent_indent='  '))

        attrs = collections.OrderedDict()
        attrs['name'] = '{}-gen'.format(name)
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = 'out.cpp'
        attrs['cmd'] = 'echo {} 1>&2; false'.format(pipes.quote(msg))
        rules.append(Rule('cxx_genrule', attrs))

        attrs = collections.OrderedDict()
        attrs['name'] = name
        attrs['srcs'] = [":{}-gen".format(name)]
        attrs['exported_headers'] = [":{}-gen".format(name)]
        attrs['visibility'] = ['PUBLIC']
        rules.append(Rule('cxx_library', attrs))

        return rules

    def version_universe_matches(self, universe, constraints):
        """
        Return whether the given universe matches the given constraints.
        """

        for project, version in constraints:

            # Look up the version universes version of this project.
            universe_version = universe.get(project)
            if universe_version is None:
                raise ValueError(
                    'version universe {!r} has no version entry for {!r} '
                    'when considering constraints: {!r}'
                    .format(
                        self.get_version_universe_name(universe),
                        project,
                        constraints))

            # If it's not the same, we don't match.
            if version != universe_version:
                return False

        return True

    def get_version_universe_name(self, universe):
        return ','.join('{}-{}'.format(p, v)
                        for p, v in sorted(universe.items()))

    def get_version_universe(self, constraints):
        """
        Find a version universe that matches the given constraints.
        """

        for universe in self._context.third_party_config['version_universes']:
            if self.version_universe_matches(universe, constraints):
                return self.get_version_universe_name(universe)

        raise ValueError(
            'cannot match a version universe to constraints: {!r}'
            .format(constraints))

    def get_python_platform(self, platform, major_version, flavor=""):
        """
        Constructs a Buck Python platform string from the given parameters.
        """
        # See `get_python_platforms_config` in `tools/build/buck/gen_modes.py`:
        return ('{flavor}py{major}-{platform}'
                .format(flavor=(flavor + '_' if flavor else ''),
                        major=major_version,
                        platform=platform))

    def get_allowed_args(self):
        return None

    def convert(self, base_path, **kwargs):
        raise NotImplementedError()

    def gen_typing_config(
        self,
        target_name,
        base_path='',
        srcs=(),
        deps=(),
        typing=False,
        typing_options='',
        visibility=None,
    ):
        """
        Generate typing configs, and gather those for our deps
        """
        return Rule('genrule', gen_typing_config_attrs(
            target_name=target_name,
            base_path=base_path,
            srcs=srcs,
            deps=deps,
            typing=typing,
            typing_options=typing_options,
            visibility=visibility,
        ))
