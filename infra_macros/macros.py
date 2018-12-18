#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

# Since this is used as a Buck build def file, we can't normal linting
# as we'll get complaints about magic definitions like `get_base_path()`.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import functools

with allow_unsafe_import():
    import os


macros_py_dir = os.path.dirname(__file__)
MACRO_LIB_DIR = os.path.join(macros_py_dir, 'macro_lib')

# We're allowed to do absolute paths in add_build_file_dep and include_defs
# so we do. This helps with problems that arise from relative paths when you
# have sibling cells. e.g. below, before, macros// would determine that the
# root was at /, even if we were including the macros defs from cell1//
# Example layout that this helps with:
# /.buckconfig
#  includes = macros//macros.py
# /cell1/.buckconfig
#  includes = macros//macros.py
# /macros/.buckconfig
# /macros/macros.py
load('@fbcode_macros//build_defs:config.bzl', 'config')
load('@fbcode_macros//build_defs/lib:cpp_common.bzl', 'cpp_common')
load('@fbcode_macros//build_defs/lib:visibility.bzl', 'get_visibility_for_base_path')
load("@fbcode_macros//build_defs:auto_headers.bzl", "AutoHeaders", "get_auto_headers")
include_defs('//{}/converter.py'.format(MACRO_LIB_DIR), 'converter')
include_defs('//{}/constants.py'.format(MACRO_LIB_DIR), 'constants')

__all__ = []


CXX_RULES = set([
    'cpp_benchmark',
    'cpp_binary',
    'cpp_java_extension',
    'cpp_library',
    'cpp_lua_extension',
    'cpp_python_extension',
    'cpp_unittest',
])

def rule_handler(rule_type, **kwargs):
    """
    Callback that fires when a TARGETS rule is evaluated, converting it into
    one or more Buck rules.
    """

    attributes = kwargs

    # For full auto-headers support, add in the recursive header glob rule
    # as a dep. This is only used in fbcode for targets that don't fully
    # specify their dependencies, and it will be going away in the future
    if (config.get_add_auto_headers_glob() and
            rule_type in CXX_RULES and
            AutoHeaders.RECURSIVE_GLOB == get_auto_headers(
                attributes.get('auto_headers'))):
        deps = list(attributes.get('deps', []))
        deps.append(cpp_common.default_headers_library())
        attributes['deps'] = deps

    # Set default visibility
    attributes['visibility'] = get_visibility_for_base_path(
        attributes.get('visibility'),
        attributes.get('name'),
        get_base_path())

    # Convert the fbconfig/fbmake rule into one or more Buck rules.
    converter.convert(rule_type, attributes)


# Helper rule to throw an error when accessing raw Buck rules.
def invalid_buck_rule(rule_type, *args, **kwargs):
    raise ValueError(
        '{rule}(): unsupported access to raw Buck rules! '
        'Please use {alternative} instead. '
        'See https://fburl.com/fbcode-targets for all available rules'
        .format(
            rule=rule_type,
            alternative=constants.BUCK_TO_FBCODE_MAP.get(
                rule_type,
                'supported fbcode rules'
            )
        )
    )


# Helper rule to ignore a Buck rule if requested by buck config.
def ignored_buck_rule(rule_type, *args, **kwargs):
    pass


__all__.append('install_converted_rules')
def install_converted_rules(globals):
    # Prevent direct access to raw BUCK UI, as it doesn't go through our
    # wrappers.
    for rule_type in constants.BUCK_RULES:
        globals[rule_type] = functools.partial(invalid_buck_rule, rule_type)

    all_rule_types = constants.FBCODE_RULES + \
        ['buck_' + r for r in constants.BUCK_RULES]
    for rule_type in all_rule_types:
        globals[rule_type] = functools.partial(rule_handler, rule_type)

    # If fbcode.enabled_rule_types is specified, then all rule types that aren't
    # whitelisted should be redirected to a handler that's a no-op. For example,
    # only a small set of rules are supported for folks building on laptop.
    enabled_rule_types = read_config('fbcode', 'enabled_rule_types', None)
    if enabled_rule_types is not None:
        enabled_rule_types = (r.strip() for r in enabled_rule_types.split(','))
        for rule_type in set(all_rule_types) - set(enabled_rule_types):
            globals[rule_type] = functools.partial(ignored_buck_rule, rule_type)
