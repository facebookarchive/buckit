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


class CppLibraryExternalConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(CppLibraryExternalConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return 'prebuilt_cxx_library'

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
            include_dir=None,
            deps=(),
            external_deps=[],
            propagated_pp_flags=[],
            linker_flags=[],
            soname=None,
            mode=None,
            shared_only=None,  # TODO: Deprecate?
            imports=None,
            implicit_project_deps=True,
            supports_omnibus=None,
            visibility=None,
            link_without_soname=False,
            static_lib=None,
            static_pic_lib=None,
            shared_lib=None,
            versioned_static_lib=None,
            versioned_static_pic_lib=None,
            versioned_shared_lib=None,
            versioned_header_dirs=None,
            ):

        # We currently have to handle `cpp_library_external` rules in fbcode,
        # until we move fboss's versioned tp2 deps to use Buck's version
        # support.

        # TODO: Just take this as a parameter
        platform = (
            self.get_tp2_build_dat(base_path)['platform']
            if self.is_tp2(base_path) else None)

        # Normalize include dir param.

        # TODO: If type == str
        if isinstance(include_dir, basestring):
            include_dir = [include_dir]

        attributes = collections.OrderedDict()

        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility

        attributes['soname'] = soname
        if link_without_soname:
            attributes['link_without_soname'] = link_without_soname

        should_not_have_libs = header_only or (mode is not None and not mode)
        if force_shared or shared_only or should_not_have_libs:
            static_lib = None
            static_pic_lib = None
            versioned_static_lib = None
            versioned_static_pic_lib = None
        if force_static or should_not_have_libs:
            shared_lib = None
            versioned_shared_lib = None

        attributes['static_lib'] = static_lib
        attributes['static_pic_lib'] = static_pic_lib
        attributes['shared_lib'] = shared_lib
        attributes['header_dirs'] = include_dir
        attributes['versioned_static_lib'] = versioned_static_lib
        attributes['versioned_static_pic_lib'] = versioned_static_pic_lib
        attributes['versioned_shared_lib'] = versioned_shared_lib
        attributes['versioned_header_dirs'] = versioned_header_dirs

        # Parse external deps.
        out_ext_deps = []
        for target in external_deps:
            out_ext_deps.append(self.normalize_external_dep(target))

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
