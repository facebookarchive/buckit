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

import collections
import functools
import itertools
import pipes

with allow_unsafe_import():
    import warnings
    warnings.simplefilter("ignore", ImportWarning)
    warnings.simplefilter("ignore", DeprecationWarning)
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import os
    import pkgutil
    import sys
    import textwrap


def find_cell_root(start_path):
    # Keep going up until we find a .buckconfig file
    path = os.path.split(start_path)[0]
    path_terminal = os.path.splitdrive(path)[0] or '/'

    add_build_file_dep('//.buckconfig')
    while path != path_terminal:
        if os.path.exists(os.path.join(path, '.buckconfig')):
            return path
        path = os.path.split(path)[0]
    raise Exception(
        "Could not find .buckconfig in a directory above {}".format(start_path))


macros_py_dir = os.path.dirname(__file__)
CELL_ROOT = find_cell_root(macros_py_dir)
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
load('@fbcode_macros//build_defs:build_mode.bzl', 'build_mode')
load('@fbcode_macros//build_defs:config.bzl', 'config')
load('@fbcode_macros//build_defs:platform.bzl', platform_utils='platform')
load('@fbcode_macros//build_defs:visibility.bzl', 'get_visibility_for_base_path')
include_defs('//{}/converter.py'.format(MACRO_LIB_DIR), 'converter')
include_defs('//{}/constants.py'.format(MACRO_LIB_DIR), 'constants')
include_defs('//{}/global_defns.py'.format(MACRO_LIB_DIR), 'global_defns')
include_defs('//{}/cxx_sources.py'.format(MACRO_LIB_DIR), 'cxx_sources')
include_defs('//{}/rule.py'.format(MACRO_LIB_DIR), 'rule_mod')
include_defs('//{}/convert/base.py'.format(MACRO_LIB_DIR), 'base')
include_defs('//{}/convert/cpp.py'.format(MACRO_LIB_DIR), 'cpp')

__all__ = []

def get_oss_third_party_config():
    interpreter = read_config('python#py3', 'interpreter', 'python3')
    if interpreter.endswith('python3'):
        with allow_unsafe_import():
            import subprocess
        print(
            'No explicit interpreter was provided, so python3 version '
            'detection is falling back to running the "python3" command. '
            'Update python#py3.interpreter in your .buckconfig in order to '
            'not have to run this command each time, and avoid potential '
            'problems with buck overcaching', file=sys.stderr)
        try:
            py3_version = subprocess.check_output([interpreter, '--version'])
            py3_version = py3_version.encode('utf-8').split()[1]
        except subprocess.CalledProcessError:
            print(
                '{} --version failed. python3 version could '
                'not be determined'.format(interpreter), file=sys.stderr)
            raise
    else:
        py3_version = interpreter.rpartition('python')[-1]
    py3_version = '.'.join(py3_version.split('.')[0:2])

    default_platform = read_config('cxx', 'default_platform', 'default')
    default_arch = read_config('buckit', 'architecture', 'x86_64')
    gcc_version = read_config('buckit', 'gcc_version', '4.9')
    return {
        'platforms': {
            default_platform: {
                'architecture': default_arch,
                'build': {
                    'auxiliary_versions': {},
                    'projects': {
                        'python': [('2.7', '2.7'), (py3_version, py3_version)],
                    },
                },
                'tools': {
                    'projects': {
                        'gcc': gcc_version,
                    },
                },
            },
        },
        'version_universes': [
            {
                'python': '2.7',
            },
            {
                'python': py3_version,
            },
        ],
    }


if config.get_third_party_config_path():
    # Load the third-party config.
    config_path = os.path.join(CELL_ROOT, config.get_third_party_config_path())
    add_build_file_dep('//' + config.get_third_party_config_path())
    with open(config_path) as f:
        code = compile(f.read(), config_path, 'exec')
    vals = {}
    eval(code, vals)
    third_party_config = vals['config']
else:
    # If we're not given a file with a third-party config (like on dev servers)
    # don't try to load the third-party-config
    third_party_config = get_oss_third_party_config()


# Add the `util` class supporting fbconfig/fbmake globs.
class Empty(object):
    pass
util = Empty()
util.files = lambda *patterns: glob(patterns)
__all__.append('util')


CXX_RULES = set([
    'cpp_benchmark',
    'cpp_binary',
    'cpp_java_extension',
    'cpp_library',
    'cpp_lua_extension',
    'cpp_python_extension',
    'cpp_unittest',
])


HEADERS_RULE_CACHE = set()


def require_default_headers_rule():
    name = '__default_headers__'
    if get_base_path() not in HEADERS_RULE_CACHE:
        HEADERS_RULE_CACHE.add(get_base_path())
        buck_platform = platform_utils.get_buck_platform_for_current_buildfile()
        cxx_library(
            name=name,
            default_platform=buck_platform,
            defaults={'platform': buck_platform},
            exported_headers=(
                glob(['**/*' + ext for ext in cxx_sources.HEADER_EXTS])
            ),
        )
    return ':' + name


def rule_handler(context, globals, rule_type, **kwargs):
    """
    Callback that fires when a TARGETS rule is evaluated, converting it into
    one or more Buck rules.
    """

    # Wrap the TARGETS rule into a `Rule` object.
    rule = rule_mod.Rule(type=rule_type, attributes=kwargs)

    # For full auto-headers support, add in the recursive header glob rule
    # as a dep. This is only used in fbcode for targets that don't fully
    # specify their dependencies, and it will be going away in the future
    if (config.get_add_auto_headers_glob() and
            rule.type in CXX_RULES and
            AutoHeaders.RECURSIVE_GLOB == cpp.CppConverter.get_auto_headers(
                rule.attributes.get('headers'),
                rule.attributes.get('auto_headers'),
                read_config)):
        deps = list(rule.attributes.get('deps', []))
        deps.append(require_default_headers_rule())
        rule.attributes['deps'] = deps

    # Convert the fbconfig/fbmake rule into one or more Buck rules.
    base_path = get_base_path()
    context['buck_ops'] = (
        base.BuckOperations(
            add_build_file_dep,
            glob,
            include_defs,
            read_config))
    context['build_mode'] = build_mode.get_build_modes_for_base_path(base_path).get(context['mode'])
    context['third_party_config'] = third_party_config
    context['config'] = config

    # Set default visibility
    rule.attributes['visibility'] = get_visibility_for_base_path(
        rule.attributes.get('visibility'),
        rule.attributes.get('name'),
        base_path)

    results = converter.convert(base.Context(**context), base_path, rule)
    # Instantiate the Buck rules that got converted successfully.
    for converted in results:
        eval(converted.type, globals)(**converted.attributes)

# Export global definitions.
for key, val in global_defns.__dict__.iteritems():
    if not key.startswith('_'):
        globals()[key] = val
        __all__.append(key)


# Helper rule to throw an error when accessing raw Buck rules.
def invalid_buck_rule(rule_type, *args, **kwargs):
    raise ValueError(
        '{rule}(): unsupported access to raw Buck rules! '
        'Please use supported fbcode rules (https://fburl.com/fbcode-targets) '
        'instead.'
        .format(rule=rule_type))


# Helper rule to ignore a Buck rule if requested by buck config.
def ignored_buck_rule(rule_type, *args, **kwargs):
    pass


def _install_converted_rules(globals, **context_kwargs):
    old_globals = globals.copy()

    # Prevent direct access to raw BUCK UI, as it doesn't go through our
    # wrappers.
    for rule_type in constants.BUCK_RULES:
        globals[rule_type] = functools.partial(invalid_buck_rule, rule_type)

    all_rule_types = constants.FBCODE_RULES + \
        ['buck_' + r for r in constants.BUCK_RULES]
    for rule_type in all_rule_types:
        globals[rule_type] = functools.partial(
            rule_handler, context_kwargs, old_globals, rule_type)

    # If fbcode.enabled_rule_types is specified, then all rule types that aren't
    # whitelisted should be redirected to a handler that's a no-op. For example,
    # only a small set of rules are supported for folks building on laptop.
    enabled_rule_types = read_config('fbcode', 'enabled_rule_types', None)
    if enabled_rule_types is not None:
        enabled_rule_types = map(unicode.strip, enabled_rule_types.split(','))
        for rule_type in set(all_rule_types) - set(enabled_rule_types):
            globals[rule_type] = functools.partial(ignored_buck_rule, rule_type)


__all__.append('install_converted_rules')
def install_converted_rules(globals, **context_kwargs):
    context_kwargs = {
        'default_compiler': config.get_default_compiler_family(),
        'global_compiler': config.get_global_compiler_family(),
        'coverage': config.get_coverage(),
        'link_style': config.get_default_link_style(),
        'mode': config.get_build_mode(),
        'sanitizer': config.get_sanitizer() if config.get_sanitizer() else None,
        'lto_type': config.get_lto_type(),
    }
    _install_converted_rules(globals, **context_kwargs)
