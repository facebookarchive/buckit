#!/usr/bin/env python2

# Copyright 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.


"""
Wheels as dependencies
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

with allow_unsafe_import():  # noqa: magic
    import collections
    import textwrap


def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


base = import_macro_lib('convert/base')
Rule = import_macro_lib('rule').Rule
load("@fbcode_macros//build_defs/lib:python_typing.bzl",
     "get_typing_config_target")

load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:python_wheel.bzl", "python_wheel")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:python_typing.bzl", "gen_typing_config")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")


def _wheel_override_version_check(name, platform_versions):
    wheel_platform = read_config("python", "wheel_platform_override")
    if wheel_platform:

        wheel_platform = "py3-{}".format(wheel_platform)
        building_platform = "py3-{}".format(
            platform_utils.get_platform_for_current_buildfile()
        )

        # Setting defaults to "foo" and "bar" so that they're different in case both return None
        if platform_versions.get(building_platform, "foo") != platform_versions.get(
            wheel_platform, "bar"
        ):
            print(
                "We're showing this warning because you're building for {0} "
                "and the default version of {4} for this platform ({2}) "
                "doesn't match the default version for {1} ({3}). "
                "The resulting binary might not work on {0}. "
                "Make sure there is a {0} wheel for {3} version of {4}.".format(
                    wheel_platform,
                    building_platform,
                    platform_versions.get(wheel_platform, "None"),
                    platform_versions.get(building_platform, "None"),
                    name,
                )
            )


def _error_rules(name, msg, visibility=None):
    """
    Return rules which generate an error with the given message at build
    time.
    """

    msg = 'ERROR: ' + msg
    msg = "\n".join(textwrap.wrap(msg, 79, subsequent_indent='  '))

    genrule_name = '{}-gen'.format(name)
    fb_native.cxx_genrule(
        name=genrule_name,
        visibility=get_visibility(visibility, genrule_name),
        out='out.cpp',
        cmd='echo {} 1>&2; false'.format(shell.quote(msg)),
    )

    fb_native.cxx_library(
        name=name,
        srcs=[":{}-gen".format(name)],
        exported_headers=[":{}-gen".format(name)],
        visibility=['PUBLIC'],
    )


class PyWheelDefault(base.Converter):
    """
    Produces a RuleTarget named after the base_path that points to the
    correct platform default as defined in data
    """
    def get_fbconfig_rule_type(self):
        return 'python_wheel_default'

    def get_allowed_args(self):
        return {
            'platform_versions'
        }

    def convert_rule(self, base_path, platform_versions, visibility):
        name = paths.basename(base_path)

        _wheel_override_version_check(name, platform_versions)

        # If there is no default for either py2 or py3 for the given platform
        # Then we should fail to return a rule, instead of silently building
        # but not actually providing the wheel.  To do this, emit and add
        # platform deps onto "error" rules that will fail at build time.
        platform_versions = collections.OrderedDict(platform_versions)
        for platform in platform_utils.get_platforms_for_host_architecture():
            py2_plat = platform_utils.get_buck_python_platform(platform, major_version=2)
            py3_plat = platform_utils.get_buck_python_platform(platform, major_version=3)
            present_for_any_python_version = (
                py2_plat in platform_versions or py3_plat in platform_versions
            )
            if not present_for_any_python_version:
                msg = (
                    '{}: wheel does not exist for platform "{}"'
                    .format(name, platform))
                error_name = '{}-{}-error'.format(name, platform)
                _error_rules(error_name, msg)
                platform_versions[py2_plat] = error_name
                platform_versions[py3_plat] = error_name

        # TODO: Figure out how to handle typing info from wheels
        if get_typing_config_target():
            gen_typing_config(name, visibility=visibility)
        fb_native.python_library(
            name=name,
            visibility=visibility,
            platform_deps=[
                ('{}$'.format(platform_utils.escape(py_platform)), [':' + version])
                for py_platform, version in sorted(platform_versions.items())
            ],
        )

    def convert(self, base_path, platform_versions, visibility=None):
        """
        Entry point for converting python_wheel rules
        """
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        self.convert_rule(base_path, platform_versions, visibility=visibility)

        return []


class PyWheel(base.Converter):
    def get_fbconfig_rule_type(self):
        return 'python_wheel'

    def get_allowed_args(self):
        return {
            'version',
            'platform_urls',
            'deps',
            'external_deps',
            'tests',
        }

    def convert(self, base_path, version, platform_urls, visibility=None, **kwargs):
        """
        Entry point for converting python_wheel rules
        """
        python_wheel(
            version=version,
            platform_urls=platform_urls,
            visibility=visibility,
            **kwargs
        )

        return []
