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

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:modules.bzl", "modules")

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("{}:fbcode_target.py".format(macro_root),
     "RootRuleTarget",
     "RuleTarget",
     "ThirdPartyRuleTarget")
load("@fbcode_macros//build_defs:modules.bzl", "modules")


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
            modules_local_submodule_visibility=False,
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

        # Parse dependencies.
        dependencies = []
        # Support intra-project deps.
        for dep in deps:
            assert dep.startswith(':')
            dependencies.append(
                ThirdPartyRuleTarget(os.path.dirname(base_path), dep[1:]))
        if implicit_project_deps and self.is_tp2(base_path):
            project = base_path.split(os.sep)[3]
            dependencies.append(self.get_tp2_project_target(project))
        for dep in external_deps:
            dependencies.append(self.normalize_external_dep(dep))

        lang_ppflags = collections.defaultdict(list)
        versioned_lang_ppflags = []

        # If modules are enabled, automatically build a module from the module
        # map found in the first include dir, if one exists.
        if modules.enabled() and self.is_tp2(base_path):

            # Add implicit toolchain module deps.
            dependencies.extend(
                map(target.parse_target, modules.get_implicit_module_deps()))

            # Set a default module name.
            module_name = (
                modules.get_module_name(
                    'third-party',
                    self.get_tp2_project_name(base_path),
                    name))

            def maybe_add_module(module_rule_name, inc_dirs, ppflags):

                # If the first include dir has a `module.modulemap` file, auto-
                # generate a module rule for it.
                if (not inc_dirs or
                        not native.glob([paths.join(inc_dirs[0],
                                                    'module.modulemap')])):
                    return

                # Create the module compilation rule.
                self._gen_tp2_cpp_module(
                    base_path,
                    name=module_rule_name,
                    module_name=module_name,
                    header_dir=inc_dirs[0],
                    dependencies=dependencies,
                    local_submodule_visibility=modules_local_submodule_visibility,
                    flags=propagated_pp_flags,
                    visibility=['//{}:{}'.format(base_path, name)],
                )

                # Add module location to exported C++ flags.
                ppflags.setdefault('cxx', [])
                ppflags['cxx'].append(
                    '-fmodule-file={}=$(location :{})'
                    .format(module_name, module_rule_name))

            # Add implicit module rule for the main header dir.
            maybe_add_module(name + '-module', include_dir, lang_ppflags)

            # Add implicit module rules for versioned header dirs.
            for idx, (constraints, inc_dirs) in enumerate(versioned_header_dirs or ()):
                versioned_lang_ppflags.append((constraints, {}))
                maybe_add_module(
                    name + '-module-v' + str(idx),
                    inc_dirs,
                    versioned_lang_ppflags[-1][1])

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

        if lang_ppflags:
            attributes['exported_lang_preprocessor_flags'] = lang_ppflags

        if versioned_lang_ppflags:
            attributes['versioned_exported_lang_preprocessor_flags'] = (
                versioned_lang_ppflags)

        if dependencies:
            attributes['exported_deps'] = (
                self.format_deps(dependencies, platform=platform))

        if supports_omnibus is not None:
            attributes['supports_merged_linking'] = supports_omnibus

        return [Rule(self.get_buck_rule_type(), attributes)]
