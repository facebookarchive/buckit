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

import os
import subprocess
import collections

from . import base
from .base import ThirdPartyRuleTarget
from ..rule import Rule

PYTHON = ThirdPartyRuleTarget('python', 'python')
PYTHON3 = ThirdPartyRuleTarget('python3', 'python')

def get_soname(lib):
    try:
        output = subprocess.check_output(['objdump', '-p', lib])
    except subprocess.CalledProcessError:
        return None
    for line in output.splitlines():
        if line.strip():
            parts = line.split()
            if parts[0] == 'SONAME':
                return parts[1]
    return None


class CppLibraryExternalConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(CppLibraryExternalConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return 'prebuilt_cxx_library'

    def get_solib_path(self, base_path, name, lib_dir, lib_name):
        """
        Get the path to the shared library.
        """

        parts = []

        parts.append(base_path)

        # If this is a tp2 project, add in the build subdir of any build.
        if self.is_tp2(base_path):
            project_builds = self.get_tp2_project_builds(base_path)
            build = project_builds.values()[0]
            parts.append(build.subdir)

        parts.append(lib_dir)
        parts.append('lib{}.so'.format(lib_name or name))

        return os.path.join(*parts)

    def convert(
            self,
            base_path,
            name=None,
            link_whole=None,
            force_shared=None,
            force_static=None,
            header_only=None,
            lib_name=None,
            lib_dir='lib',
            include_dir=['include'],
            deps=(),
            external_deps=[],
            propagated_pp_flags=[],
            linker_flags=[],
            soname=None,
            mode=None,
            shared_only=None,
            imports=None,
            implicit_project_deps=True):

        # We currently have to handle `cpp_library_external` rules in fbcode,
        # until we move fboss's versioned tp2 deps to use Buck's version
        # support.
        platform = (
            self.get_tp2_build_dat(base_path)['platform']
            if self.is_tp2(base_path) else None)

        attributes = collections.OrderedDict()

        attributes['name'] = name

        # If the `soname` parameter isn't set, try to guess it from inspecting
        # the DSO.
        solib_path = self.get_solib_path(base_path, name, lib_dir, lib_name)
        self._context.buck_ops.add_build_file_dep('//' + solib_path)
        # Use size to avoid parse warnings for linker scripts
        # 228 was the largest linker script, and 5K the smallest real .so file
        if (soname is None and os.path.exists(solib_path) and
             os.path.getsize(solib_path) > 2048):
            soname = get_soname(solib_path)
        if soname is not None:
            attributes['soname'] = soname
        if soname is None and os.path.exists(solib_path):
            attributes['link_without_soname'] = True

        attributes['lib_name'] = lib_name or name
        attributes['lib_dir'] = lib_dir

        if force_static:
            attributes['force_static'] = force_static

        if force_shared:
            attributes['provided'] = force_shared

        # We're header only if explicitly set, or if `mode` is set to an empty
        # list.
        if header_only or (mode is not None and not mode):
            attributes['header_only'] = True

        if link_whole:
            attributes['link_whole'] = link_whole

        if include_dir:
            if isinstance(include_dir, basestring):
                include_dir = [include_dir]
            attributes['include_dirs'] = include_dir

        out_linker_flags = []
        for flag in linker_flags:
            out_linker_flags.append('-Xlinker')
            out_linker_flags.append(flag)
        # TODO(#8334786): There's some strange hangs when linking third-party
        # `--as-needed`.  Enable when these are debugged.
        if self._context.mode.startswith('dev'):
            out_linker_flags.append('-Wl,--no-as-needed')
        attributes['exported_linker_flags'] = out_linker_flags

        if propagated_pp_flags:
            attributes['exported_preprocessor_flags'] = propagated_pp_flags

        # Parse external deps.
        out_ext_deps = []
        for target in external_deps:
            out_ext_deps.append(self.normalize_external_dep(target))

        # Setup the version sub-dir parameter, which tells Buck to select the
        # correct build based on the versions of transitive deps it selected.
        if self.is_tp2(base_path):
            project_builds = (
                self.get_tp2_project_builds(
                    base_path,
                    None
                    if implicit_project_deps
                    else {d.base_path for d in out_ext_deps}))
            if (len(project_builds) > 1 or
                    project_builds.values()[0].subdir != ''):
                versioned_sub_dir = []
                for build in project_builds.values():
                    versioned_sub_dir.append(
                        (build.project_deps, build.subdir))
                attributes['versioned_sub_dir'] = versioned_sub_dir

        dependencies = []

        # Parse inter-project deps.
        for dep in deps:
            assert dep.startswith(':')
            dependencies.append(
                self.get_dep_target(
                    ThirdPartyRuleTarget(os.path.dirname(base_path), dep[1:]),
                    source=dep))

        # Add the implicit dep to our own project rule.
        if implicit_project_deps and self.is_tp2(base_path):
            dependencies.append(self.get_tp2_project_dep(base_path))

        # Add external deps.k
        for dep in out_ext_deps:
            dependencies.append(self.get_dep_target(dep, platform=platform))

        if dependencies:
            attributes['exported_deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
