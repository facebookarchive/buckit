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
import functools
import os
import re

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))


class CppJvmLibrary(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'cpp_jvm_library'

    def get_allowed_args(self):
        return set([
            'name',
            'major_version',
        ])

    def convert(self, base_path, name, major_version, visibility=None):
        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility

        def formatter(flags, platform, _):
            arch = self.get_platform_architecture(platform)
            # Remap arch to JVM-specific names.
            arch = {'x86_64': 'amd64'}.get(arch, arch)
            return [flag.format(arch=arch, platform=platform) for flag in flags]

        jvm_path = '/usr/local/fb-jdk-{}-{{platform}}'.format(major_version)

        # We use include/library paths to wrap the custom FB JDK installed at
        # system locations.  As such, we don't properly hash various components
        # (e.g. headers, libraries) pulled into the build.  Longer-term, we
        # should move the FB JDK into tp2 to do this properly.
        attrs['exported_platform_preprocessor_flags'] = (
            self.format_platform_param(
                functools.partial(
                    formatter,
                    ['-isystem',
                     os.path.join(jvm_path, 'include'),
                     '-isystem',
                     os.path.join(jvm_path, 'include', 'linux')])))
        attrs['exported_platform_linker_flags'] = (
            self.format_platform_param(
                functools.partial(
                    formatter,
                    ['-L{}/jre/lib/{{arch}}/server'.format(jvm_path),
                     '-Wl,-rpath={}/jre/lib/{{arch}}/server'.format(jvm_path),
                     '-ljvm'])))

        return [Rule('cxx_library', attrs)]
