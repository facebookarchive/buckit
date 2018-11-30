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
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:build_info.bzl", "build_info")
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
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

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

    def merge_platform_deps(self, dst, src):
        for platform, deps in src.iteritems():
            dst.setdefault(platform, [])
            dst[platform].extend(deps)

    def is_test(self, buck_rule_type):
        return buck_rule_type.endswith('_test')

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
        source_attrs['labels'] = ["generated"]
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
        lib_attrs['labels'] = ["generated"]
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
        if cpp_flags.get_lto_is_enabled():
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

    def copy_rule(self, src, name, out=None, propagate_versions=False, visibility=None, labels=None):
        """
        Returns a `genrule` which copies the given source.
        """

        if out is None:
            out = name

        attrs = collections.OrderedDict()
        attrs['name'] = name
        if labels is not None:
            attrs['labels'] = labels
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
            visibility=None,
            labels=None):
        """
        Generate a rule which creates an output dir with the given paths merged
        with the merged directories of it's dependencies.
        """

        cmds = []

        for dep in sorted(deps):
            cmds.append('rsync -a $(location {})/ "$OUT"'.format(dep))
        for src in sorted(paths):
            src = src_and_dep_helpers.get_source_name(src)
            dst = os.path.join('"$OUT"', base_path, src)
            cmds.append("mkdir -p {}".format(os.path.dirname(dst)))
            cmds.append("cp {} {}".format(src, dst))

        fb_native.genrule(
            name = name,
            labels = labels or [],
            visibility = visibility if visibility != None else None,
            out = os.curdir,
            srcs = sorted(paths),
            cmd = " && ".join(cmds),
        )

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
            labels=["generated"],
            visibility=visibility,
        ))
