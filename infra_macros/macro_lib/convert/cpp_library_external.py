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

with allow_unsafe_import():
    import os
    import subprocess

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("{}:fbcode_target.py".format(macro_root),
     "RootRuleTarget",
     "RuleTarget",
     "ThirdPartyRuleTarget")


PYTHON = ThirdPartyRuleTarget('python', 'python')
PYTHON3 = ThirdPartyRuleTarget('python3', 'python')

Inputs = (
    collections.namedtuple(
        'Inputs',
        ['static_lib',
         'static_pic_lib',
         'shared_lib',
         'includes']))


def prefix_path(prefix, path):
    if path is None:
        return None
    return os.path.join(prefix, path)


def prefix_inputs(prefix, inputs):
    return Inputs(
        static_lib=prefix_path(prefix, inputs.static_lib),
        static_pic_lib=prefix_path(prefix, inputs.static_pic_lib),
        shared_lib=prefix_path(prefix, inputs.shared_lib),
        includes=[os.path.join(prefix, i) for i in inputs.includes])


class CppLibraryExternalConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(CppLibraryExternalConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return 'prebuilt_cxx_library'

    def get_lib(self, name, lib_dir, lib_name, ext):
        """
        Get a base-path relative library path with the given extension.
        """

        parts = []
        parts.append(lib_dir)
        parts.append('lib{}{}'.format(lib_name or name, ext))
        return os.path.join(*parts)

    def get_lib_path(self, base_path, name, lib_dir, lib_name, ext):
        """
        Get the path to a library.
        """

        parts = []

        parts.append(base_path)

        # If this is a tp2 project, add in the build subdir of any build.
        if self.is_tp2(base_path):
            project_builds = self.get_tp2_project_builds(base_path)
            build = project_builds.values()[0]
            parts.append(build.subdir)

        parts.append(self.get_lib(name, lib_dir, lib_name, ext))

        return os.path.join(*parts)

    def get_inputs(
            self,
            base_path,
            name,
            lib_dir,
            lib_name,
            includes,
            header_only,
            force_shared,
            force_static,
            shared_only,
            mode,
            relevant_deps=None):
        """
        Get the base-path relative libraries and include dirs in the form of a
        tuple of unversioned inputs and versioned inputs.
        """

        # Build the base inputs relative the base path.
        inputs = (
            Inputs(
                static_lib=self.get_lib(name, lib_dir, lib_name, '.a'),
                static_pic_lib=self.get_lib(name, lib_dir, lib_name, '_pic.a'),
                shared_lib=self.get_lib(name, lib_dir, lib_name, '.so'),
                includes=includes))

        # Header-only rules have no libs.
        if header_only or (mode is not None and not mode):
            inputs = (
                inputs._replace(
                    static_lib=None,
                    static_pic_lib=None,
                    shared_lib=None))

        # Filter out static libs based on parameters.
        if force_shared or shared_only:
            inputs = inputs._replace(static_lib=None, static_pic_lib=None)

        # Filter out shared libs based on paramaters.
        if force_static:
            inputs = inputs._replace(shared_lib=None)

        # Filter out shared libs based on existence.
        if inputs.shared_lib is not None:
            shared_path = (
                self.get_lib_path(base_path, name, lib_dir, lib_name, '.so'))
            self._context.buck_ops.add_build_file_dep('//' + shared_path)
            if not os.path.exists(shared_path):
                inputs = inputs._replace(shared_lib=None)

        # Filter out static pic libs based on existence.
        if inputs.static_pic_lib is not None:
            static_pic_path = (
                self.get_lib_path(base_path, name, lib_dir, lib_name, '_pic.a'))
            self._context.buck_ops.add_build_file_dep('//' + static_pic_path)
            if not os.path.exists(static_pic_path):
                inputs = inputs._replace(static_pic_lib=None)

        # Setup the version sub-dir parameter, which tells Buck to select the
        # correct build based on the versions of transitive deps it selected.
        if self.is_tp2(base_path):
            project_builds = (
                self.get_tp2_project_builds(
                    base_path,
                    relevant_deps=relevant_deps))
            if (len(project_builds) > 1 or
                    project_builds.values()[0].subdir != ''):
                versioned_inputs = Inputs([], [], [], [])
                for build in project_builds.values():
                    build_inputs = prefix_inputs(build.subdir, inputs)
                    if build_inputs.shared_lib is not None:
                        versioned_inputs.shared_lib.append(
                            (build.project_deps, build_inputs.shared_lib))
                    if build_inputs.static_lib is not None:
                        versioned_inputs.static_lib.append(
                            (build.project_deps, build_inputs.static_lib))
                    if build_inputs.static_pic_lib is not None:
                        versioned_inputs.static_pic_lib.append(
                            (build.project_deps, build_inputs.static_pic_lib))
                    versioned_inputs.includes.append(
                        (build.project_deps, build_inputs.includes))
                return None, versioned_inputs

        return inputs, None

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
            implicit_project_deps=True,
            supports_omnibus=None,
            visibility=None,
            link_without_soname=False,
            static_lib=None,  # ignored for now
            static_pic_lib=None,  # ignored for now
            shared_lib=None,  # ignored for now
            versioned_static_lib=None,  # ignored for now
            versioned_static_pic_lib=None,  # ignored for now
            versioned_shared_lib=None,  # ignored for now
            versioned_header_dirs=None,  # ignored for now
            ):

        # We currently have to handle `cpp_library_external` rules in fbcode,
        # until we move fboss's versioned tp2 deps to use Buck's version
        # support.
        platform = (
            self.get_tp2_build_dat(base_path)['platform']
            if self.is_tp2(base_path) else None)

        # Normalize include dir param.
        if isinstance(include_dir, basestring):
            include_dir = [include_dir]

        attributes = collections.OrderedDict()

        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility

        attributes['soname'] = soname
        if link_without_soname:
            attributes['link_without_soname'] = link_without_soname

        # Parse external deps.
        out_ext_deps = []
        for target in external_deps:
            out_ext_deps.append(self.normalize_external_dep(target))

        # Install the libs and includes.
        inputs, versioned_inputs = (
            self.get_inputs(
                base_path,
                name,
                lib_dir,
                lib_name,
                include_dir,
                header_only,
                force_shared,
                force_static,
                shared_only,
                mode,
                relevant_deps=(
                    None
                    if implicit_project_deps
                    else {d.base_path for d in out_ext_deps})))
        if inputs is not None:
            attributes['static_lib'] = inputs.static_lib
            attributes['static_pic_lib'] = inputs.static_pic_lib
            attributes['shared_lib'] = inputs.shared_lib
            attributes['header_dirs'] = inputs.includes
        if versioned_inputs is not None:
            if versioned_inputs.static_lib:
                attributes['versioned_static_lib'] = versioned_inputs.static_lib
            if versioned_inputs.static_pic_lib:
                attributes['versioned_static_pic_lib'] = (
                    versioned_inputs.static_pic_lib)
            if versioned_inputs.shared_lib:
                attributes['versioned_shared_lib'] = versioned_inputs.shared_lib
            attributes['versioned_header_dirs'] = versioned_inputs.includes

        # Set preferred linkage.
        if force_shared or shared_only:
            attributes['preferred_linkage'] = 'shared'
        elif force_static:
            attributes['preferred_linkage'] = 'static'

        if force_shared:
            attributes['provided'] = True

        # We're header only if explicitly set, or if `mode` is set to an empty
        # list.
        if header_only or (mode is not None and not mode):
            attributes['header_only'] = True

        if link_whole:
            attributes['link_whole'] = link_whole

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

        if supports_omnibus is not None:
            attributes['supports_merged_linking'] = supports_omnibus

        return [Rule(self.get_buck_rule_type(), attributes)]
