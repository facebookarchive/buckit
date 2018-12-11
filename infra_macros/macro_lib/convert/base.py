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
import json


load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@bazel_skylib//lib:paths.bzl", "paths")


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


_LTO_FLAG = ["-flto"]


class Converter(object):

    def __init__(self, context):
        self._context = context
        self._tp2_build_dat_cache = {}

    def get_third_party_root(self, platform):
        if config.get_third_party_use_platform_subdir():
            return paths.join(
                config.get_third_party_buck_directory(),
                platform)
        else:
            return config.get_third_party_buck_directory()

    def get_tp2_dep_path(self, project, platform):
        """
        Return the path within third-party for the given project. This will be
        the directory, not a specific target or binary. Based on configuration,
        and the path may be modified to fit fbcode's layout
        """

        if config.get_third_party_use_build_subdir():
            return paths.join(self.get_third_party_root(platform), 'build', project)
        else:
            return project

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

    def get_tp2_build_dat(self, base_path):
        """
        Load the TP2 metadata for the TP2 project at the given base path.
        """

        build_dat = self._tp2_build_dat_cache.get(base_path)
        if build_dat is not None:
            return build_dat

        fbsource_root = read_config('fbsource', 'repo_relative_path', '..');
        build_dat_name = paths.join(fbsource_root, "fbcode", base_path, 'build.dat')
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

    def get_allowed_args(self):
        return None

    def convert(self, base_path, **kwargs):
        raise NotImplementedError()
