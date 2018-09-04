"""
Helper functions for managing fbcode build info.

https://our.intern.facebook.com/intern/dex/buck/fbcode-build-info/
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import collections

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_choice")


# Build info settings which affect rule keys.
ExplicitBuildInfo = (
    collections.namedtuple(
        'ExplicitBuildInfo',
        ['build_mode',
         'compiler',
         'package_name',
         'package_release',
         'package_version',
         'platform',
         'rule',
         'rule_type']))


def get_build_info_mode(base_path, name):
    """
    Return the build info style to use for the given rule.
    """

    mode = (
        read_choice(
            'fbcode',
            'build_info',
            ['full', 'stable', 'none'],
            default='none'))

    # Make sure we're not using full build info when building core tools,
    # otherwise we could introduce nondeterminism in rule keys.
    if core_tools.is_core_tool(base_path, name):
        mode = "stable"

    return mode


def get_explicit_build_info(
        base_path,
        name,
        rule_type,
        platform,
        compiler):
    """
    Return the build info which can/should affect rule keys (causing rebuilds
    if it changes), and is passed into rules via rule-key-affecting parameters.
    This is contrast to "implicit" build info, which must not affect rule keys
    (e.g. build time, build user), to avoid spurious rebuilds.
    """

    mode = get_build_info_mode(base_path, name)
    assert mode in ['full', 'stable']

    # We consider package build info explicit, as we must re-build binaries if
    # it changes, regardless of whether nothing else had changed (e.g.
    # T22942388).
    #
    # However, we whitelist core tools and never set this explicitly, to avoid
    # transitively trashing rule keys.
    package_name = None
    package_version = None
    package_release = None
    if mode == 'full' and not core_tools.is_core_tool(base_path, name):
        package_name = read_config('build_info', 'package_name')
        package_version = read_config('build_info', 'package_version')
        package_release = read_config('build_info', 'package_release')

    return ExplicitBuildInfo(
        build_mode=config.get_build_mode(),
        compiler=compiler,
        package_name=package_name,
        package_release=package_release,
        package_version=package_version,
        platform=platform,
        rule='fbcode:{}:{}'.format(base_path, name),
        rule_type=rule_type)
