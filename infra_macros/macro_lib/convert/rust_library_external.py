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

from . import base
from ..rule import Rule


class RustLibraryExternalConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'rust_external_library'

    def get_buck_rule_type(self):
        return 'prebuilt_rust_library'

    def convert(self,
                base_path,
                name=None,
                rlib=None,
                crate=None,
                deps=(),
                licenses=(),
                visibility=None,
                external_deps=()):

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['rlib'] = rlib

        if crate:
            attributes['crate'] = crate

        if licenses:
            attributes['licenses'] = licenses

        if visibility:
            attributes['visibility'] = visibility

        dependencies = []
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))

        for target in external_deps:
            dependencies.append(self.convert_external_build_target(target))

        if dependencies:
            attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
