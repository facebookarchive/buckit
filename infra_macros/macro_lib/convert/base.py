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
from distutils.version import LooseVersion
import functools
import json
import os
import pipes
import platform as platmod
import re
import shlex

from ..rule import Rule
from ..target import RuleTarget
from .. import target


SANITIZERS = {
    'address': 'asan',
    'address-only': 'asan-only',
    'address-undefined': 'asan-ubsan',
    'thread': 'tsan',
    'undefined': 'ubsan',
}


def SanitizerTarget(lib):
    return RuleTarget('fbcode', 'tools/build/sanitizers', lib + '-cpp')


SANITIZER_DEPS = {
    'address': SanitizerTarget('asan'),
    'address-only': SanitizerTarget('asan-only'),
    'address-undefined': SanitizerTarget('asan-ubsan'),
    'thread': SanitizerTarget('tsan'),
    'undefined': SanitizerTarget('ubsan'),
}


# Support the `allocators` parameter, which uses a keyword to select
# a memory allocator dependency. These are pulled from in buckconfig's
# fbcode.allocators.X property. The value is a comma delimited list of
# targets
ALLOCATORS = {
    'jemalloc',
    'jemalloc_debug',
    'tcmalloc',
    'malloc',
}


MACRO_PATTERN = (
    re.compile('\\$\\((?P<name>[^)\\s]+)(?: (?P<args>[^)]*))?\\)'))


Context = collections.namedtuple(
    'Context',
    [
        'buck_ops',
        'build_mode',
        'compiler',
        'coverage',
        'link_style',
        'mode',
        'sanitizer',
        'supports_lto',
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


def RootRuleTarget(base_path, name):
    return RuleTarget(None, base_path, name)


def ThirdPartyRuleTarget(project, rule_name):
    return RuleTarget(project, project, rule_name)


CXX_BUILD_INFO_TEMPLATE = """\
#include <stdint.h>

const char* const BuildInfo_kBuildMode = "{build_mode}";
const char* const BuildInfo_kBuildTool = "{build_tool}";
const char* const BuildInfo_kHost = "{host}";
const char* const BuildInfo_kPackageName = "{package_name}";
const char* const BuildInfo_kPackageVersion = "{package_version}";
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


def is_collection(obj):
    """
    Return whether the object is a array-like collection.
    """

    for typ in (list, set, tuple):
        if isinstance(obj, typ):
            return True

    return False


class RuleError(Exception):
    pass


class Converter(object):

    def __init__(self, context):
        self._context = context
        self._platform_file_cache = {}
        self._tp2_build_dat_cache = {}
        self._core_tools = None

    def get_default_platform(self):
        """
        Return the default fbcode platform we're building against.
        """
        # In fbcode, we have more elaborate configurations for various
        # "platforms". We require this to be set to something valid.
        # Outside of fbcode, we just pass the macro lib a dictionary of
        # platforms and specify 'default' as the only platform. This allows
        # us to not branch the codepaths at all in code that wants platform
        # information.
        if self._context.config.require_platform:
            return self._context.buck_ops.read_config('fbcode', 'platform', None)
        else:
            return self._context.buck_ops.read_config('cxx', 'default_platform', 'default')

    def parse_platform_file(self, filename):
        """
        Parse the given platform file and return its platform.
        """

        platform = None

        with open(filename) as f:
            for line in f:
                line = line.strip()
                # Ignore empty lines and lines starting with '#'
                if not line or line.startswith('#'):
                    continue
                # Ensure that there is only one non-comment line
                if platform is not None:
                    raise Exception('found multiple platform lines in "%s"' %
                                    (filename,))
                platform = line

        # Make sure we found a platform name
        if platform is None:
            raise Exception('no platform information present in "%s"' %
                            (filename,))

        # Make sure the name is valid
        if platform not in self.get_platforms():
            raise Exception('invalid platform specified in "%s"' %
                            (filename,))

        return platform

    def find_platform_for_path(self, base_path):
        """
        Walk up the dir tree searching for a platform specified in a PLATFORM
        file.
        """

        # If we've cached this platform file, return it.
        if base_path in self._platform_file_cache:
            return self._platform_file_cache[base_path]

        platform = None

        # If there's a platform file in this dir, parse it and return its
        # platform.  We support both `FBCODE_PLATFORM` and `PLATFORM`, as the
        # former is more specific and less likely to collide with directory
        # names (which is more likely on case-insensitive filesystems).
        platform_names = ['FBCODE_PLATFORM', 'PLATFORM']
        for platform_name in platform_names:
            platform_file = os.path.join(base_path, platform_name)
            self._context.buck_ops.add_build_file_dep('//' + platform_file)
            if os.path.isfile(platform_file):
                platform = self.parse_platform_file(platform_file)
                break

        # Otherwise, walk up the dir tree.
        if platform is None and base_path:
            dirpath = os.path.split(base_path)[0]
            platform = self.find_platform_for_path(dirpath)

        # Cache and return the result.
        self._platform_file_cache[base_path] = platform
        return platform

    def get_platform(self, base_path):
        """
        Get the fbcode platform to use for the given base path.
        """

        # First, try to find the platform from a `PLATFORM` file.
        if self.read_bool('fbcode', 'platform_files', True):
            platform = self.find_platform_for_path(base_path)
            if platform is not None:
                return platform

        # Otherwise, use the global default.
        return self.get_default_platform()

    def get_platforms(self):
        """
        Return all fbcode platforms we can build against.
        """

        platforms = set()

        for platform, config in (
                self._context.third_party_config['platforms'].iteritems()):
            # We only support native building, so exclude platforms spporting
            # incompatible architectures.
            if platmod.machine() == config['architecture']:
                platforms.add(platform)

        return sorted(platforms)

    def get_third_party_root(self, platform):
        if self._context.config.third_party_use_platform_subdir:
            return os.path.join(
                self._context.config.third_party_buck_directory,
                platform)
        else:
            return self._context.config.third_party_buck_directory

    def get_third_party_build_root(self, platform):
        if self._context.config.third_party_use_build_subdir:
            return os.path.join(self.get_third_party_root(platform), 'build')
        else:
            return self.get_third_party_root(platform)

    def get_repo_root(self, repo, platform):
        if repo is None:
            return ''
        elif (not self._context.config.unknown_cells_are_third_party or
              self._context.buck_ops.read_config('repositories', repo)):
            return ''
        else:
            return self.get_third_party_build_root(platform)

    def get_third_party_config(self, platform):
        return self._context.third_party_config['platforms'][platform]

    def get_platforms_for_arch(self, arch):
        """
        Return all platforms building for the given arch.
        """

        platforms = []

        platform_configs = self._context.third_party_config['platforms']
        for name, config in platform_configs.items():
            if arch == config['architecture']:
                platforms.append(name)

        return platforms

    def get_platform_flags_from_arch_flags(self, arch_flags):
        """
        Format a dict of architecture names to flags into a platform flag list
        for Buck.
        """

        out_platform_flags = []

        for arch, flags in arch_flags.items():
            platforms = self.get_platforms_for_arch(arch)
            if platforms:
                out_platform_flags.append(
                    ('|'.join('^' + re.escape(p) + '$' for p in platforms),
                     flags))

        return out_platform_flags

    def get_tool_version(self, platform, project):
        conf = self._context.third_party_config['platforms'][platform]
        return LooseVersion(conf['tools']['projects'][project])

    def get_auxiliary_versions(self):
        config = self.get_third_party_config(self.get_default_platform())
        return config['build']['auxiliary_versions']

    def get_target(self, repo, path, name):
        """
        Return the target for a given cell, path, and target name

        If fbcode.unknown_cells_are_third_party is True, and the repo is not
        found in .buckconfig, then a third-party directory structure is assumed
        and no cell is used
        """
        cell = repo
        if(repo and
                self._context.config.unknown_cells_are_third_party and
                self._context.buck_ops.read_config(
                    'repositories', repo) is None):
            cell = None

        return '{}//{}:{}'.format(cell or '', path, name)

    def get_tp2_tool_path(self, project, platform=None):
        """
        Return the path within third-party for the given project. This will be
        the directory, not a specific target or binary. Based on configuration,
        and the path may be modified to fit fbcode's layout
        """

        if platform is None:
            platform = self.get_default_platform()

        if self._context.config.third_party_use_tools_subdir:
            return os.path.join(
                self.get_third_party_root(platform),
                'tools',
                project)
        else:
            return os.path.join(self.get_third_party_root(platform), project)

    def get_tool_target(self, target, platform=None):
        """
        Return the target for the tool described by the given RuleTarget.
        """

        if platform is None:
            platform = self.get_default_platform()

        return self.get_target(
            target.repo,
            self.get_tp2_tool_path(target.base_path, platform),
            target.name)

    def get_tp2_dep_path(self, project, platform=None):
        """
        Return the path within third-party for the given project. This will be
        the directory, not a specific target or binary. Based on configuration,
        and the path may be modified to fit fbcode's layout
        """

        if platform is None:
            platform = self.get_default_platform()

        if self._context.config.third_party_use_build_subdir:
            return os.path.join(self.get_third_party_root(platform), 'build', project)
        else:
            return project

    def get_dep_target(self, target, platform=None, source=None):
        """
        Format a Buck-style build target from the given RuleTarget
        """

        assert target.base_path is not None, str(target)

        if platform is None:
            platform = self.get_default_platform()

        repo_root = self.get_repo_root(target.repo, platform)

        return self.get_target(
            target.repo,
            os.path.join(repo_root, target.base_path),
            target.name)

    def format_deps(self, deps, platform=None):
        """
        Takes a list of deps and returns a new list of formatted deps
        appropriate `deps` parameter.
        """

        return [self.get_dep_target(d, platform=platform) for d in deps]

    def normalize_external_dep(self, raw_target, lang_suffix=''):
        """
        Normalize the various ways users can specify an external dep into a
        RuleTarget
        """

        parsed, version = (
            target.parse_external_dep(
                raw_target,
                lang_suffix=lang_suffix))

        # OSS support: Make repo default to the base path.
        if parsed.repo is None:
            parsed = parsed._replace(repo=parsed.base_path)

        # If the parsed version for this project is listed as an auxiliary
        # version in the config, then redirect this dep to use the alternate
        # project name it's installed as.
        project = os.path.basename(parsed.base_path)
        if (version is not None and
                version in self.get_auxiliary_versions().get(project, [])):
            parsed = (
                parsed._replace(base_path=parsed.base_path + '-' + version))

        return parsed

    def convert_external_build_target(self, target, lang_suffix=''):
        """
        Convert the given build target reference from an externel dep TARGETS
        file reference.
        """

        parsed = self.normalize_external_dep(target, lang_suffix=lang_suffix)
        return self.get_dep_target(parsed, source=target)

    def normalize_dep(self, raw_target, base_path=None):
        """
        Convert the given build target into a RuleTarget
        """

        # A 'repo' is used as the cell name when generating a target except
        # when:
        #  - repo is None. This means that the rule is in the root cell
        #  - fbcode.unknown_cells_are_third_party is True. This will resolve
        #    unknown repositories as third-party libraries

        # This is the normal path for buck style dependencies. We do a little
        # parsing, but nothing too crazy. This allows OSS users to use the
        # FB macro library, but not have to use fbcode naming conventions
        if not self._context.config.fbcode_style_deps:
            if raw_target.startswith('@/'):
                raise ValueError(
                    'rule name must not start with "@/" in repositories with '
                    'fbcode style deps disabled')
            cell_and_target = raw_target.split('//', 2)
            path, rule = cell_and_target[-1].split(':')
            repo = None
            if len(cell_and_target) == 2 and cell_and_target[0]:
                repo = cell_and_target[0]
            path = path or base_path
            return RuleTarget(repo, path, rule)

        parsed = (
            target.parse_target(
                raw_target,
                default_base_path=base_path))

        # Normally in the monorepo, you can reference other directories
        # directly. When not in the monorepo, we need to map to a correct cell
        # for third-party use. A canonical example is folly. It is first-party
        # to Facebook, but third-party to OSS users, so we need to toggle what
        # '@/' means a little.
        # ***
        # We'll assume for now that all cells' names match their directory in
        # the monorepo.
        # ***
        # We can probably add more configuration later if necessary.
        if parsed.repo is None:
            if self._context.config.fbcode_style_deps_are_third_party:
                repo = parsed.base_path.split(os.sep)[0]
            else:
                repo = self._context.config.current_repo_name
            parsed = parsed._replace(repo=repo)

        # Some third party dependencies fall under rules like
        # '@/fbcode:project:rule'. Let's normalize fbcode to None so that we
        # know it's under the root cell
        if parsed.repo == self._context.config.current_repo_name:
            parsed = parsed._replace(repo=None)

        return parsed

    def get_fbcode_target(self, target):
        """
        Convert a Buck style rule name back into an fbcode one.
        """

        if self._context.config.fbcode_style_deps and target.startswith('//'):
            target = '@/' + target[2:]

        return target

    def convert_build_target(self, base_path, target, platform=None):
        """
        Convert the given build target into a buck build target.
        """

        parsed = self.normalize_dep(target, base_path=base_path)
        return self.get_dep_target(parsed, source=target, platform=platform)

    def convert_source(self, base_path, src):
        """
        Convert a source, which may refer to an in-repo source or a rule that
        generates it, to a Buck-compatible source path reference.
        """

        # If this src starts with the special build target chars, parse it as
        # a build target.  We also parse it as a build target if we see the
        # typical Buck absolute target prefix, so generate a proper error
        # message.
        if src[0] in ':@' or src.startswith('//'):
            src = self.convert_build_target(base_path, src)

        return src

    def convert_source_list(self, base_path, srcs):
        converted = []
        for src in srcs:
            converted.append(self.convert_source(base_path, src))
        return converted

    def convert_source_map(self, base_path, srcs):
        converted = {}
        for k, v in srcs.iteritems():
            converted[self.get_source_name(k)] = (
                self.convert_source(base_path, v))
        return converted

    def convert_blob_with_macros(
            self,
            base_path,
            blob,
            extra_handlers=None,
            platform=None):
        """
        Convert build targets inside macros.
        """

        handlers = {}

        def convert_target_expander(name, target):
            return '$({} {})'.format(
                name,
                self.convert_build_target(base_path, target, platform=platform))

        def as_is_converter(name, *args):
            return '$({})'.format(' '.join([name] + list(args)))

        # Install handlers to convert the build targets inside the `exe` and
        # `location` macros.
        handlers['exe'] = functools.partial(convert_target_expander, 'exe')
        handlers['classpath'] = (
            functools.partial(convert_target_expander, 'classpath'))
        handlers['location'] = (
            functools.partial(convert_target_expander, 'location'))
        handlers['FBMAKE_BIN_ROOT'] = (
            functools.partial(as_is_converter, 'FBMAKE_BIN_ROOT'))

        # Install extra, passed in handlers.
        if extra_handlers is not None:
            handlers.update(extra_handlers)

        def repl(m):
            name = m.group('name')
            args = m.group('args')
            handler = handlers.get(name)
            if handler is None:
                raise ValueError(
                    'unsupported macro {!r} in {!r}'
                    .format(name, blob))
            return handler(args) if args is not None else handler()

        return MACRO_PATTERN.sub(repl, blob)

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

    def format_platform_deps(self, deps):
        """
        Takes a map of fbcode platform names to lists of deps and converts to
        an output list appropriate for Buck's `platform_deps` parameter.
        """

        out_deps = []

        for platform, pdeps in sorted(deps.iteritems()):
            out_deps.append(
                # Buck expects the platform name as a regex, so anchor and
                # escape it for literal matching.
                ('^{}$'.format(re.escape(platform)),
                 self.format_deps(pdeps, platform=platform)))

        return out_deps

    def to_platform_deps(self, external_deps, platforms=None):
        """
        Convert a list of parsed targets to a mapping of platforms to deps.
        """

        platform_deps = collections.OrderedDict()

        if platforms is None:
            platforms = self.get_platforms()

        # Add the platform-specific dep for each platform.
        for dep in external_deps:
            for platform in platforms:
                platform_deps.setdefault(platform, []).append(dep)

        return platform_deps

    def format_all_deps(self, deps, platform=None):
        """
        Return a tuple of formatted internal and external deps, to be installed
        in rules via the `deps` and `platform_deps` parameters, respectively.
        """

        out_deps = []
        out_deps.extend(self.get_dep_target(d) for d in deps if d.repo is None)
        # If we have an explicit platform (as is the case with tp2 projects),
        # we can pass the tp2 deps using the `deps` parameter.
        if platform is not None:
            out_deps.extend(
                self.get_dep_target(d, platform=platform)
                for d in deps if d.repo is not None)

        out_platform_deps = []
        if platform is None:
            out_platform_deps.extend(
                self.format_platform_deps(
                    self.to_platform_deps(
                        [d for d in deps if d.repo is not None])))

        return out_deps, out_platform_deps

    def is_test(self, buck_rule_type):
        return buck_rule_type.endswith('_test')

    def convert_labels(self, *labels):
        new_labels = []
        new_labels.append('buck')
        new_labels.append(self._context.mode)
        new_labels.append(self._context.compiler)
        if self._context.sanitizer is not None:
            new_labels.append(SANITIZERS[self._context.sanitizer])
        new_labels.extend(labels)
        return new_labels

    def get_build_mode(self):
        return self._context.build_mode

    def get_source_name(self, src):
        """
        Get the logical name of the given source.
        """

        # If this is a build target, extract the name from the `=<name>`
        # suffix.
        if src[0] in '/@:':
            try:
                _, name = src.split('=')
            except ValueError:
                raise ValueError(
                    'generated source target {!r} is missing `=<name>` suffix'
                    .format(src))
            return name

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

    def read_bool(self, section, field, default=None):
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
        else:
            raise KeyError(
                '`{}:{}`: no value set'.format(section, field))

    def read_flags(self, section, field, default=None):
        """
        Read a list of quoted flags from `.buckconfig`.
        """

        val = self._context.buck_ops.read_config(section, field)
        if val is not None:
            return shlex.split(val)
        elif default is not None:
            return default
        else:
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

    def is_core_tool(self, base_path, name):
        """
        Returns whether the target represented by the given base path and name
        is considered a "core" tool.
        """

        # Outside of fbcode, the rulekey thrash should not exist, so skip
        # in all cases
        if not self._context.config.core_tools_path:
            return False

        # Load core tools from the path, if it hasn't been already.
        if self._core_tools is None:
            self._context.buck_ops.add_build_file_dep(
                '//' + self._context.config.core_tools_path)
            tools = set()
            with open(self._context.config.core_tools_path) as of:
                for line in of:
                    if not line.startswith('#'):
                        tools.add(line.strip())
            self._core_tools = tools

        target = '//{}:{}'.format(base_path, name)
        return target in self._core_tools

    def get_compiler_langs(self):
        """
        The languages which general compiler flag apply to.
        """

        return (
            'asm',
            'assembler',
            'c_cpp_output',
            'cuda_cpp_output',
            'cxx_cpp_output')

    def get_compiler_general_langs(self):
        """
        The languages which general compiler flag apply to.
        """

        return ('assembler', 'c_cpp_output', 'cxx_cpp_output')

    def get_compiler_flags(self, base_path):
        """
        Return a dict mapping languages to base compiler flags.
        """

        # Initialize the compiler flags dictionary.
        compiler_flags = collections.OrderedDict()
        for lang in self.get_compiler_langs():
            compiler_flags[lang] = []

        # The set of language we apply "general" compiler flags to.
        c_langs = self.get_compiler_general_langs()

        # Apply the general sanitizer/coverage flags.
        for lang in c_langs:
            compiler_flags[lang].extend(self.get_sanitizer_flags())
            compiler_flags[lang].extend(self.get_coverage_flags(base_path))

        # Apply flags from the build mode file.
        build_mode = self.get_build_mode()
        if build_mode is not None:

            # Apply language-specific build mode flags.
            compiler_flags['c_cpp_output'].extend(build_mode.settings.CFLAGS)
            compiler_flags['cxx_cpp_output'].extend(
                build_mode.settings.CXXFLAGS)

            # Apply compiler-specific build mode flags.
            for lang in c_langs:
                if self._context.compiler == 'gcc':
                    compiler_flags[lang].extend(build_mode.settings.GCCFLAGS)
                else:
                    compiler_flags[lang].extend(build_mode.settings.CLANGFLAGS)

            # Cuda always uses GCC.
            compiler_flags['cuda_cpp_output'].extend(
                build_mode.settings.GCCFLAGS)

        # Add in command line flags last.
        compiler_flags['c_cpp_output'].extend(self.get_extra_cflags())
        compiler_flags['cxx_cpp_output'].extend(self.get_extra_cxxflags())

        return compiler_flags

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
        if self.is_core_tool(base_path, name):
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

    def get_extra_cflags(self):
        """
        Get extra C compiler flags to build with.
        """

        return self.read_flags('cxx', 'extra_cflags', default=())

    def get_extra_cxxflags(self):
        """
        Get extra C++ compiler flags to build with.
        """

        return self.read_flags('cxx', 'extra_cxxflags', default=())

    def get_extra_cppflags(self):
        """
        Get extra C preprocessor flags to build with.
        """

        return self.read_flags('cxx', 'extra_cppflags', default=())

    def get_extra_cxxppflags(self):
        """
        Get extra C++ preprocessor flags to build with.
        """

        return self.read_flags('cxx', 'extra_cxxppflags', default=())

    def get_extra_ldflags(self):
        """
        Get extra linker flags to build with.
        """

        return self.read_flags('cxx', 'extra_ldflags', default=())

    def get_link_style(self):
        """
        The link style to use for native binary rules.
        """

        # Initialize the link style using the one set via `gen_modes.py`.
        link_style = self._context.link_style

        # If we're using TSAN, we need to build PIEs, which requires PIC deps.
        # So upgrade to `static_pic` if we're building `static`.
        if self._context.sanitizer == 'thread' and link_style == 'static':
            link_style = 'static_pic'

        return link_style

    def get_build_info_mode(self):
        """
        Return the build info style to use.
        """

        return self.read_choice(
            'fbcode',
            'build_info',
            ['full', 'stable', 'none'])

    def get_build_info_linker_flags(
            self,
            base_path,
            name,
            rule_type,
            platform):
        """
        Get the linker flags to configure how the linker embeds build info.
        """

        ldflags = []

        mode = self.get_build_info_mode()

        # Make sure we're not using non-deterministic build info when caching
        # is enabled.
        cache_links = self.read_bool('cxx', 'cache_links', True)
        if mode == 'full' and cache_links:
            raise ValueError(
                'cannot use `full` build info when `cxx.cache_links` is set')

        # Pass the build info mode to the linker.
        ldflags.append('--build-info=' + mode)

        # Add in build information.
        ldflags.append('--build-info-build-mode=' + self._context.mode)
        ldflags.append('--build-info-platform=' + platform)
        ldflags.append('--build-info-rule=fbcode:' + base_path + ':' + name)
        ldflags.append('--build-info-rule-type=' + rule_type)

        return ldflags

    def get_binary_ldflags(self, base_path, name, rule_type):
        """
        Return ldflags set via various `.buckconfig` settings.
        """

        ldflags = []

        # If we're using TSAN, we need to build PIEs.
        if self._context.sanitizer == 'thread':
            ldflags.append('-pie')

        return ldflags

    def get_lto_level(self):
        """
        Returns the user-specific LTO parallelism level.
        """

        default = 32 if self._context.supports_lto else 0
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
        if not self._context.supports_lto:
            raise ValueError('build mode doesn\'t supoprt LTO')

        # Read the LTO parallelism level from the config, where `0` disables
        # LTO.
        lto_level = self.get_lto_level()
        assert lto_level > 0, lto_level

        # When linking with LTO, we need to pass compiler flags that affect
        # code generation back into the linker.  Since we don't actually
        # discern code generation flags from language specific flags, just
        # pass all our C/C++ compiler flags in.
        compiler_flags = self.get_compiler_flags(base_path)
        section = 'cxx#{}'.format(platform)
        flags.extend(self.read_flags(section, 'cflags', []))
        flags.extend(compiler_flags['c_cpp_output'])
        flags.extend(self.read_flags(section, 'cxxflags', []))
        flags.extend(compiler_flags['cxx_cpp_output'])

        # This warning can fire on unreachable paths after a lot of inlining
        # If it doesn't show up in normal compiles, not much point in
        # showing it here.
        flags.append('-Wno-free-nonheap-object')

        # Set the linker that flags that will run LTO.
        flags.append('-fuse-linker-plugin')
        flags.append('-flto={}'.format(lto_level))

        return flags

    def get_ldflags(
            self,
            base_path,
            name,
            rule_type,
            binary=False,
            strip_mode=None,
            build_info=False,
            lto=False,
            platform=None):
        """
        Return linker flags to apply to links.
        """

        ldflags = []

        # 1. Add in build-mode ldflags.
        build_mode = self.get_build_mode()
        if build_mode is not None:
            ldflags.extend(build_mode.settings.LDFLAGS)

        # 2. Add flag to strip debug symbols.
        if strip_mode is None:
            strip_mode = self.get_strip_mode(base_path, name)
        strip_ldflag = self.get_strip_ldflag(strip_mode)
        if strip_ldflag is not None:
            ldflags.append(strip_ldflag)

        # 3. Add in flags specific for linking a binary.
        if binary:
            ldflags.extend(self.get_binary_ldflags(base_path, name, rule_type))

        # 4. Add in the build info linker flags.
        # In OSS, we don't need to actually use the build info (and the
        # linker will not understand these options anyways) so skip in that case
        if build_info and self._context.config.use_build_info_linker_flags:
            ldflags.extend(
                self.get_build_info_linker_flags(
                    base_path,
                    name,
                    rule_type,
                    platform))

        # 5. If enabled, add in LTO linker flags.
        if self.is_lto_enabled():
            if self._context.compiler == 'clang':
                # Clang does not support fat LTO objects, so we build everything
                # as IR only, and must also link everything with -flto
                ldflags.append('-flto')
            else:
                assert(self._context.compiler == 'gcc')
                # GCC has fat LTO objects, where we build everything as both IR
                # and object code and then conditionally opt-in here, at link-
                # time, based on "enable_lto" in the TARGETS file.
                if lto:
                    ldflags.extend(self.get_gcc_lto_ldflags(base_path, platform))
                else:
                    ldflags.append('-fno-lto')

        # 6. Add in command-line ldflags.
        ldflags.extend(self.get_extra_ldflags())

        return ldflags

    def get_sanitizer_binary_deps(self):
        """
        Add additional dependencies needed to build with the given sanitizer.
        """

        sanitizer = self._context.sanitizer
        if sanitizer is None:
            return []
        assert self._context.compiler == 'clang'
        assert sanitizer in SANITIZER_DEPS

        deps = [
            SANITIZER_DEPS[sanitizer],
            ThirdPartyRuleTarget('glibc', 'c'),
        ]

        return deps

    def get_coverage_binary_deps(self):
        assert self._context.coverage
        assert self._context.compiler == 'clang'

        if self._context.sanitizer is None:
            return [
                RuleTarget('llvm-fb', 'llvm-fb', 'clang_rt.profile-x86_64'),
            ]
        else:
            # all coverage deps are included in the santizer deps
            return []

    def get_binary_link_deps(self, allocator='malloc'):
        """
        Return a list of dependencies that should apply to *all* binary rules
        that link C/C++ code.
        """

        deps = []

        # If we're not using a sanitizer add allocator deps.
        if self._context.sanitizer is None:
            deps.extend(self.get_allocator_deps(allocator))

        # Add in any dependencies required for sanitizers.
        deps.extend(self.get_sanitizer_binary_deps())

        # Add in any dependencies required for code coverage
        if self._context.coverage:
            deps.extend(self.get_coverage_binary_deps())

        return deps

    def get_allocator_deps(self, allocator):
        deps = []

        for rdep in self._context.config.allocators[allocator]:
            deps.append(self.normalize_dep('@/' + rdep[2:]))

        return deps

    def get_allocators(self):
        return {
            allocator: self._context.config.allocators[allocator]
            for allocator in ALLOCATORS
        }

    # Normalize the `allocator` parameter, throwing away the version
    # constraint (if there is one), since Buck doesn't support multiple
    # versions.
    def get_allocator(self, allocator=None):
        if allocator is None:
            allocator = self._context.config.default_allocator
        elif isinstance(allocator, tuple):
            allocator = allocator[0]
        return allocator

    def create_cxx_build_info_rule(
            self,
            base_path,
            name,
            rule_type,
            platform,
            linker_flags=(),
            static=True):
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
        source_attrs['out'] = source_name + '.c'
        source_attrs['cmd'] = (
            'mkdir -p `dirname $OUT` && echo {0} > $OUT'
            .format(pipes.quote(info)))
        rules.append(Rule('genrule', source_attrs))

        # Setup a rule to compile the build info C file into a library.
        lib_name = name + '-cxx-build-info-lib'
        lib_attrs = collections.OrderedDict()
        lib_attrs['name'] = lib_name
        lib_attrs['srcs'] = [':' + source_name]
        lib_attrs['compiler_flags'] = self.get_extra_cflags()
        lib_attrs['linker_flags'] = (
            list(self.get_extra_ldflags()) +
            ['-nodefaultlibs'] +
            list(linker_flags))

        # Clang does not support fat LTO objects, so we build everything
        # as IR only, and must also link everything with -flto
        if self.is_lto_enabled() and self._context.compiler == 'clang':
            lib_attrs['linker_flags'].append('-flto')

        if static:
            # Use link_whole to make sure the build info symbols are always
            # added to the binary, even if the binary does not refer to them.
            lib_attrs['link_whole'] = True
            # Use force_static so that the build info symbols are always put
            # directly in the main binary, even if dynamic linking is used.
            lib_attrs['force_static'] = True
        rules.append(Rule('cxx_library', lib_attrs))

        return RootRuleTarget(base_path, lib_name), rules

    def get_build_info(self, base_path, name, rule_type, platform):
        if self.is_core_tool(base_path, name):
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
        build_info['epochtime'] = (
            int(read_config('build_info', 'epochtime', '0')))
        build_info['host'] = read_config('build_info', 'host', '')
        build_info['package_name'] = (
            read_config('build_info', 'package_name', ''))
        build_info['package_version'] = (
            read_config('build_info', 'package_version', ''))
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

    def copy_rule(self, src, name, out=None, propagate_versions=False):
        """
        Returns a `genrule` which copies the given source.
        """

        if out is None:
            out = name

        attrs = collections.OrderedDict()
        attrs['name'] = name
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
            deps):
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
        attrs['out'] = os.curdir
        attrs['srcs'] = sorted(paths)
        attrs['cmd'] = ' && '.join(cmds)
        return Rule('genrule', attrs)

    def is_tp2(self, base_path):
        """
        Return whether the rule this `base_path` corresponds to come from
        third-party.
        """

        return base_path.startswith('third-party-buck/')

    def get_tp2_build_dat(self, base_path):
        """
        Load the TP2 metadata for the TP2 project at the given base path.
        """

        build_dat = self._tp2_build_dat_cache.get(base_path)
        if build_dat is not None:
            return build_dat

        build_dat_name = os.path.join(base_path, 'build.dat')
        self._context.buck_ops.add_build_file_dep('//' + build_dat_name)
        with open(build_dat_name) as f:
            build_dat = json.load(f)

        self._tp2_build_dat_cache[base_path] = build_dat
        return build_dat

    def get_tp2_platform(self, base_path):
        """
        Get the fbcode this tp2 project was built for.
        """

        return self.get_tp2_build_dat(base_path)['platform']

    def get_tp2_project_target_name(self):
        """
        Return the short name of the implicit TP2 project target.
        """

        return '__project__'

    def get_tp2_project_name(self, base_path):
        """
        Return the name of the TP2 project at the given base path.
        """

        return base_path.split(os.sep)[3]

    def get_tp2_project_target(self, project):
        """
        Return the TP2 project target for the given project.
        """

        return ThirdPartyRuleTarget(
            project,
            self.get_tp2_project_target_name())

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
                    self.get_dep_target(
                        self.get_tp2_project_target(project),
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
        return self.get_dep_target(
            self.get_tp2_project_target(project),
            platform=platform)

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

    def get_py2_version(self):
        conf = self.get_third_party_config(self.get_default_platform())
        return conf['build']['projects']['python'][0][1]

    def get_py3_version(self):
        conf = self.get_third_party_config(self.get_default_platform())
        return conf['build']['projects']['python'][1][1]

    def get_python_platform(self, platform, python_version):
        return 'py{}-{}'.format(python_version[0], platform)

    def get_py2_platform(self, platform):
        return self.get_python_platform(platform, self.get_py2_version())

    def get_py3_platform(self, platform):
        return self.get_python_platform(platform, self.get_py3_version())

    def get_allowed_args(self):
        return None

    def convert(self, base_path, **kwargs):
        raise NotImplementedError()
