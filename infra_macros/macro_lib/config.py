#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
List of user-configurable settings for the buck macro library
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from collections import namedtuple
import copy

_Option = namedtuple(
    'Option', ['section', 'field', 'default_value']
)
_BoolOption = namedtuple(
    'BoolOption', ['section', 'field', 'default_value']
)
_ListOption = namedtuple(
    'ListOption', ['section', 'field', 'default_value', 'delimiter']
)


def ListOption(section, field, default_value, description, delimiter=','):
    """Proxy to _ListOption, but ensure that a description is provided"""
    return _ListOption(section, field, default_value, delimiter)


def BoolOption(section, field, default_value, description):
    """Proxy to _BoolOption, but ensure that a description is provided"""
    return _BoolOption(section, field, default_value)


def Option(section, field, default_value, description):
    """Proxy to _Option, but ensure that a description is provided"""
    return _Option(section, field, default_value)


def FacebookInternalOption(section, field, default_value, description):
    """
    Proxy to _Option, but ensure that a description is provided.
    These options are intended for use entirely inside of Facebook,
    and may not yet have a good OSS analog
    """
    return _Option(section, field, default_value)


class FbcodeOptions(object):
    third_party_buck_directory = Option(
        'fbcode', 'third_party_buck_directory', '',
        'An additional directory that should be inserted into all third party '
        'paths in a monorepo')

    third_party_config_path = Option(
        'fbcode', 'third_party_config_path', '',
        'The root relative path to a python file that contains a third-party '
        'config that will be loaded. If not provided, a default one is created')

    add_auto_headers_glob = BoolOption(
        'fbcode', 'add_auto_headers_glob', False,
        'Whether to add an autoheaders dependency. This should not be used '
        'outside of the Facebook codebase, as it breaks assumptions about '
        'cross package file ownership')

    fbcode_style_deps_are_third_party = BoolOption(
        'fbcode', 'fbcode_style_deps_are_third_party', True,
        'Whether rules starting with "@/" should be converted to third-party '
        'libraries that use the first component of the path as the cell name')

    unknown_cells_are_third_party = BoolOption(
        'fbcode', 'unknown_cells_are_third_party', False,
        'Whether or not cells that are not in the [repositories] section '
        'should instead be assumed to be in the third-party directory, and '
        'follow the directory structure that fbcode uses')

    fbcode_style_deps = BoolOption(
        'fbcode', 'fbcode_style_deps', False,
        'Whether or not dependencies are fbcode-style dependencies, or buck '
        'style ones. fbcode style rules must begin with @/, and do not support '
        'cells. Buck style rules are exactly like those on buckbuild.com. This '
        'must be consistent for an entire cell')

    third_party_use_build_subdir = BoolOption(
        'fbcode', 'third_party_use_build_subdir', False,
        'If true, assume that there is a "build" sub directory in the '
        'third-party directory, and use it for third party dependencies')

    third_party_use_platform_subdir = BoolOption(
        'fbcode', 'third_party_use_platform_subdir', False,
        'Whether the third-party directory has an first level subdirectory '
        'for the platform specified by fbcode.platform')

    third_party_use_tools_subdir = BoolOption(
        'fbcode', 'third_party_use_tools_subdir', False,
        'Whether there is a tools subdirectory in third-party that should '
        'be used for things like compilers and various utilities used to '
        'build targets')

    core_tools_path = Option(
        'fbcode', 'core_tools_path', '',
        'If set, the include_def style path to a file that contains a list of '
        'core tools. This is only useful in Facebook\'s repository and is '
        'used to reduce rulekey thrashing')

    use_build_info_linker_flags = BoolOption(
        'fbcode', 'use_build_info_linker_flags', False,
        'Whether or not to provide the linker with build_info flags. These '
        'arguments go to a custom linker script at Facebook, and should not '
        'be used outside of Facebook')

    require_platform = BoolOption(
        'fbcode', 'require_platform', False,
        'If true, require that fbcode.platform is specified')

    current_repo_name = Option(
        'fbcode', 'current_repo_name', 'fbcode',
        'For rules of the form @/repo:path:rule, if repo equals this value, '
        'the rule is assumed to be underneath the root cell, rather than '
        'a third party dependency. This should not be used outside of Facebook')

    default_allocator = Option(
        'fbcode', 'default_allocator', 'malloc',
        'Which allocator to use when not specified. Pulled from '
        'fbcode.allocators below')

    allocators = {
        'jemalloc': Option(
            'fbcode', 'allocators.jemalloc', 'jemalloc//jemalloc:jemalloc',
            'The target to use if jemalloc is specified as an allocator'
        ),
        'jemalloc_debug': Option(
            'fbcode', 'allocators.jemalloc_debug',
            'jemalloc//jemalloc:jemalloc_debug',
            'The target to use if jemalloc_debug is specified as an allocator'
        ),
        'tcmalloc': Option(
            'fbcode', 'allocators.tcmalloc', 'tcmalloc//tcmalloc:tcmalloc',
            'The target to use if tcmalloc is specified as an allocator'
        ),
        'malloc': Option(
            'fbcode', 'allocators.malloc', '',
            'If provided, a target to use if malloc is specified as an allocator'
        ),
    }

    use_custom_par_args = BoolOption(
        'fbcode', 'use_custom_par_args', False,
        'If set, use custom build arguments for Facebook\'s internal pex '
        'build script'
    )

    forbid_raw_buck_rules = BoolOption(
        'fbcode', 'forbid_raw_buck_rules', False,
        'If set, forbid raw buck rules that are not in '
        'fbcode.whitelisted_raw_buck_rules'
    )

    whitelisted_raw_buck_rules = Option(
        'fbcode', 'whitelisted_raw_buck_rules', '',
        'A list of rules that are allowed to use each type of raw buck rule.'
        'This is a list of buck rule types to path:target that should be '
        'allowed to use raw buck rules. e.g. cxx_library=watchman:headers'
    )

    thrift_compiler = Option(
        'thrift', 'compiler', 'thrift//thrift/compiler:thrift',
        'The target for the top level cpp thrift compiler'
    )

    thrift2_compiler = Option(
        'thrift', 'compiler2', 'thrift//thrift/compiler/py:thrift',
        'The target for the cpp2 thrift compiler',
    )

    thrift_hs2_compiler = FacebookInternalOption(
        'thrift', 'hs2_compiler', '',
        'The target for the haskell thrift compiler',
    )

    thrift_ocaml_compiler = FacebookInternalOption(
        'thrift', 'ocaml_compiler', '',
        'The target for the OCaml thrift compiler',
    )

    thrift_swift_compiler = FacebookInternalOption(
        'thrift', 'swift_compiler', '',
        'The target for the swift thrift compiler',
    )

    thrift_templates = Option(
        'thrift', 'templates', 'thrift//thrift/compiler/generate:templates',
        'The target that generates thrift templates',
    )

    header_namespace_whitelist = Option(
        'fbcode', 'header_namespace_whitelist', '',
        'List of targets that are allowed to use header_namespace in cpp_* '
        'rules')

    auto_pch_blacklist = ListOption(
        'fbcode', 'auto_pch_blacklist', [],
        'If provided, a list of directories that should be opted out of '
        'automatically receiving precompiled headers when pch is enabled')

    build_mode = Option(
        'fbcode', 'build_mode', 'dev',
        'The name of the build mode. This affects some compiler flags that '
        'are added as well as other build settings')

    compiler_family = Option(
        'fbcode', 'compiler_family', None,
        'The family of compiler that is in use. If not set, it will be '
        'determined from the name of the cxx.compiler binary')

    coverage = BoolOption(
        'fbcode', 'coverage', False,
        'Whether to gather coverage information or not')

    default_link_style = Option(
        'defaults.cxx_library', 'type', 'static',
        'The default link style to use. This can be modified for things for '
        'different languages as necessary')

    lto_type = Option(
        'fbcode', 'lto_type', None,
        'What kind of Link Time Optimization the compiler supports')

    sanitizer = Option(
        'fbcode', 'sanitizer', None,
        'The type of sanitizer to try to use. If not set, do not use it')

    gtest_lib_dependencies = Option(
        'fbcode', 'gtest_lib_dependencies', None,
        'The targets that will provide gtest C++ tests\' gtest and gmock deps')

    gtest_main_dependency = Option(
        'fbcode', 'gtest_main_dependency', None,
        'The target that will provide gtest C++ tests\' main function')

    cython_compiler = Option(
        'cython', 'cython_compiler', None,
        'The target that will provide cython compiler')

    def __init__(self, read_config_func, allow_unsafe_import_func):
        self.read_config = read_config_func
        self.allow_unsafe_import = allow_unsafe_import_func
        self.read_values()

    def get_current_os(self):
        """
        Looks at fbcode.os_family, cxx.default_platform and finally
        platform.system() in order to determine what the current OS family is.
        This should be one of linux, mac or windows
        """
        os_family = self.read_config('fbcode', 'os_family', None)
        os_platform_to_family = {
            'linux': 'linux',
            'darwin': 'mac',
            'windows': 'windows'
        }

        if os_family:
            if os_family not in os_platform_to_family.values():
                os_family = None
        else:
            with self.allow_unsafe_import():
                import platform
            os_family = os_platform_to_family.get(platform.system().lower())
        if not os_family:
            raise KeyError(
                'Could not determine os family. Either set fbcode.os_family to '
                'a value containing linux, macos or windows, or run on one '
                'of those platforms (as determined by platform.system()')
        return os_family

    def read_boolean(self, option):
        val = self.read_config(*option)
        if val is True or val is False:
            return val
        elif val is not None:
            if val.lower() == 'true':
                return True
            elif val.lower() == 'false':
                return False
            else:
                raise TypeError(
                    '`{}:{}`: cannot coerce {!r} to bool'
                    .format(option.section, option.field, val))
        else:
            raise KeyError(
                '`{}:{}`: no value set'.format(option.section, option.field))

    def read_list(self, option):
        val = self.read_config(
            option.section, option.field, option.default_value)
        if isinstance(val, list):
            return copy.copy(val)
        elif val is not None:
            return [v for v in val.split(option.delimiter) if v]
        else:
            raise KeyError(
                '`{}:{}`: no value set'.format(option.section, option.field))

    def read_values(self):
        attrs = {}
        for attr in dir(self):
            value = getattr(self, attr)
            if isinstance(value, _Option):
                attrs[attr] = self.read_config(*value)
            elif isinstance(value, _BoolOption):
                attrs[attr] = self.read_boolean(value)
            elif isinstance(value, _ListOption):
                attrs[attr] = self.read_list(value)
            else:
                continue

        attrs['current_os'] = self.get_current_os()
        attrs['allocators'] = {
            k: filter(None, self.read_config(*v).split(','))
            for k, v in self.allocators.items()
        }
        whitelisted_raw_buck_rules = {
        }
        for rule_group in attrs['whitelisted_raw_buck_rules'].split(','):
            if not rule_group:
                continue
            rule_type, rule = rule_group.strip().split('=', 1)
            if rule_type not in whitelisted_raw_buck_rules:
                whitelisted_raw_buck_rules[rule_type] = []
            whitelisted_raw_buck_rules[rule_type].append(tuple(rule.split(':', 1)))
        attrs['whitelisted_raw_buck_rules'] = whitelisted_raw_buck_rules
        attrs['header_namespace_whitelist'] = [
            tuple(target.split(':', 1))
            for target in attrs['header_namespace_whitelist'].split()
            if target
        ]
        if not attrs['compiler_family']:
            cxx = self.read_config('cxx', 'cxx', 'gcc')
            attrs['compiler_family'] = 'clang' if 'clang' in cxx else 'gcc'
        FbcodeValues = namedtuple('FbcodeOptionsValues', attrs.keys())
        self.values = FbcodeValues(**attrs)
        return self.values


# As buck configuration is effectively global, export the parsed values as
# globals, allowing macro modules to `include_def` this file much as they'd
# use `read_config`.
values = FbcodeOptions(read_config, allow_unsafe_import).values
__all__ = []
for field in values._fields:
    globals()[field] = getattr(values, field)
    __all__.append(field)
