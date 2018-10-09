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

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")

class OCamlLibraryExternalConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'ocaml_external_library'

    def get_buck_rule_type(self):
        return 'prebuilt_ocaml_library'

    def convert(
            self,
            base_path,
            name=None,
            include_dirs=None,
            native_libs=None,
            bytecode_libs=None,
            c_libs=None,
            native_c_libs=None,
            bytecode_c_libs=None,
            deps=(),
            external_deps=(),
            native=True,
            visibility=None):

        platform = third_party.get_tp2_platform(base_path)

        attributes = collections.OrderedDict()

        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility

        attributes['lib_name'] = name
        attributes['lib_dir'] = ''
        if include_dirs:
            assert len(include_dirs) == 1
            attributes['include_dir'] = include_dirs[0]

        if native_libs:
            assert len(native_libs) == 1
            attributes['native_lib'] = native_libs[0]

        if bytecode_libs:
            assert len(bytecode_libs) == 1
            attributes['bytecode_lib'] = bytecode_libs[0]

        if c_libs:
            attributes['c_libs'] = c_libs

        if native_c_libs:
            attributes['native_c_libs'] = native_c_libs

        if bytecode_c_libs:
            attributes['bytecode_c_libs'] = bytecode_c_libs

        if not native:
            attributes['bytecode_only'] = True

        dependencies = []

        # Add the implicit dep to our own project rule.
        project_dep = self.get_tp2_project_dep(base_path)
        if project_dep is not None:
            dependencies.append(project_dep)

        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))

        for target in external_deps:
            edep = src_and_dep_helpers.normalize_external_dep(target)
            dependencies.append(
                target_utils.target_to_label(edep, platform=platform))

        if dependencies:
            attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
