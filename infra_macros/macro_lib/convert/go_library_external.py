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
include_defs("{}/fbcode_target.py".format(macro_root), "target")
include_defs("{}/rule.py".format(macro_root))


class GoLibraryExternalConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'go_external_library'

    def get_buck_rule_type(self):
        return 'prebuilt_go_library'

    def convert(self,
                base_path,
                name=None,
                package_name=None,
                library=None,
                deps=(),
                exported_deps=None,
                licenses=(),
                visibility=None):

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['library'] = library

        if package_name:
            attributes['package_name'] = package_name

        if licenses:
            attributes['licenses'] = licenses

        if visibility:
            attributes['visibility'] = visibility

        if exported_deps:
            exported_deps = [self.convert_build_target(base_path, d)
                             for d in exported_deps]
            attributes['exported_deps'] = exported_deps

        dependencies = []
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))

        attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
