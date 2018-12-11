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

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")

load("@bazel_skylib//lib:partial.bzl", "partial")
load("@bazel_skylib//lib:paths.bzl", "paths")

_FORMATTER_ARCHS = {"x86_64": "amd64"}

def _formatter_partial(flags, platform, _):
    arch = platform_utils.get_platform_architecture(platform)
    # Remap arch to JVM-specific names.
    arch = _FORMATTER_ARCHS.get(arch, arch)
    return [flag.format(arch=arch, platform=platform) for flag in flags]

class CppJvmLibrary(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'cpp_jvm_library'

    def get_allowed_args(self):
        return set([
            'name',
            'major_version',
        ])

    def convert(self, base_path, name, major_version, visibility=None):
        platform_jvm_path = '/usr/local/fb-jdk-{}-{{platform}}'.format(major_version)
        jvm_path = '/usr/local/fb-jdk-{}'.format(major_version)

        fb_native.cxx_library(
            name=name,
            visibility=get_visibility(visibility, name),
            # We use include/library paths to wrap the custom FB JDK installed at
            # system locations.  As such, we don't properly hash various components
            # (e.g. headers, libraries) pulled into the build.  Longer-term, we
            # should move the FB JDK into tp2 to do this properly.
            exported_platform_preprocessor_flags=(
                src_and_dep_helpers.format_platform_param(
                    partial.make(
                        _formatter_partial,
                        ['-isystem',
                         paths.join(platform_jvm_path, 'include'),
                         '-isystem',
                         paths.join(platform_jvm_path, 'include', 'linux'),
                         '-isystem',
                         paths.join(jvm_path, 'include'),
                         '-isystem',
                         paths.join(jvm_path, 'include', 'linux')]))),
            exported_platform_linker_flags=(
                src_and_dep_helpers.format_platform_param(
                    partial.make(
                        _formatter_partial,
                        ['-L{}/jre/lib/{{arch}}/server'.format(platform_jvm_path),
                         '-Wl,-rpath={}/jre/lib/{{arch}}/server'.format(platform_jvm_path),
                         '-L{}/jre/lib/{{arch}}/server'.format(jvm_path),
                         '-Wl,-rpath={}/jre/lib/{{arch}}/server'.format(jvm_path),
                         '-ljvm']))),
        )

        return []
