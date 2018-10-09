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


load("@fbcode_macros//build_defs:modules.bzl", "modules")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))


class CppModuleExternalConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'cpp_module_external'

    def convert(
            self,
            base_path,
            name=None,
            module_name=None,
            include_dir='include',
            external_deps=[],
            propagated_pp_flags=[],
            modules_local_submodule_visibility=False,
            implicit_project_dep=True,
            visibility=None):

        # Set a default module name.
        if module_name is None:
            module_name = (
                modules.get_module_name(
                    'third-party',
                    third_party.get_tp2_project_name(base_path),
                    name))

        # Setup dependencies.
        dependencies = []
        if implicit_project_dep:
            project = base_path.split(os.sep)[3]
            dependencies.append(third_party.get_tp2_project_target(project))
        for dep in external_deps:
            dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

        # Generate the module file.
        module_rule_name = name + '-module'
        self._gen_tp2_cpp_module(
            base_path,
            name=module_rule_name,
            module_name=module_name,
            header_dir=include_dir,
            local_submodule_visibility=modules_local_submodule_visibility,
            flags=propagated_pp_flags,
            dependencies=dependencies,
            visibility=["//{}:{}".format(base_path, name)],
        )

        # Wrap with a `cxx_library`, propagating the module map file via the
        # `-fmodule-file=...` flag in it's exported preprocessor flags so that
        # dependents can easily access the module.
        attrs = collections.OrderedDict()
        attrs['name'] = name
        out_exported_preprocessor_flags = []
        out_exported_preprocessor_flags.extend(propagated_pp_flags)
        out_exported_preprocessor_flags.append(
            '-fmodule-file={}=$(location :{})'
            .format(module_name, module_rule_name))
        attrs['exported_lang_preprocessor_flags'] = (
            {'cxx': out_exported_preprocessor_flags})
        attrs['exported_deps'] = (
            src_and_dep_helpers.format_deps(
                dependencies,
                platform=self.get_tp2_build_dat(base_path)['platform']))
        if visibility is not None:
            attrs["visibility"] = visibility
        # Setup platform default for compilation DB, and direct building.
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        attrs['default_platform'] = buck_platform
        attrs['defaults'] = {'platform': buck_platform}
        wrapper_rule = Rule('cxx_library', attrs)

        return [wrapper_rule]
