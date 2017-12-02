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

import collections
import os
import re


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


def get_url_basename(url):
    """ Urls will have an #md5 etag remove it and return the wheel name"""
    return os.path.basename(url).split('#md5')[0]


def gen_remote_wheel(url, out, sha1):
    attrs = collections.OrderedDict()
    attrs['name'] = out + '-remote'
    attrs['out'] = out
    attrs['url'] = url
    attrs['sha1'] = sha1
    return Rule('remote_file', attrs)


def gen_prebuilt_target(wheel, remote_target):
    attrs = collections.OrderedDict()
    attrs['name'] = wheel
    attrs['binary_src'] = remote_target
    return Rule('prebuilt_python_library', attrs)


class PyWheelDefault(base.Converter):
    """
    Produces a RuleTarget named after the base_path that points to the
    correct platform default as defined in data
    """
    def get_fbconfig_rule_type(self):
        return 'python_wheel_default'

    def get_allowed_args(self):
        return {
            'data'
        }

    def convert_rule(self, base_path, data):
        platform = self.get_default_platform()

        # If there is no default for either py2 or py3 for the given platform
        # Then we should fail to return a rule, instead of silently building
        # but not actually providing the wheel
        has_defaults = any(
            (py_platform in data
                for py_platform in (
                    self.get_py3_platform(platform),
                    self.get_py2_platform(platform),
                )
             )
        )
        if not has_defaults:
            return

        attrs = collections.OrderedDict()
        attrs['name'] = os.path.basename(base_path)
        attrs['platform_deps'] = [
            ('^{}$'.format(re.escape(py_platform)), [':' + version])
            for py_platform, version in data.items()
        ]
        yield Rule('python_library', attrs)

    def convert(self, base_path, data):
        """
        Entry point for converting python_wheel rules
        """
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        for rule in self.convert_rule(base_path, data):
            yield rule


class PyWheel(base.Converter):
    def get_fbconfig_rule_type(self):
        return 'python_wheel'

    def convert_rule(
        self,
        base_path,
        version,
        data,  # Dict[str, Tuple(str, str)]   # platform -> url, sha1
        deps=(),
        external_deps=(),
        tests=(),
    ):
        # We don't need duplicate targets if we have multiple usage of URLs
        urls = set(data.values())
        wheel_targets = {}  # Dict[str, str]      # url -> prebuilt_target_name

        # Setup all the remote_file and prebuilt_python_library targets
        for url, sha1 in urls:
            wheel = get_url_basename(url)
            rule = gen_remote_wheel(url, wheel, sha1)
            yield rule
            rule = gen_prebuilt_target(wheel, rule.target_name)
            yield rule
            wheel_targets[url] = rule.target_name

        attrs = collections.OrderedDict()
        attrs['name'] = version
        # Use platform_deps to rely on the correct wheel target for
        # each platform
        attrs['platform_deps'] = [
            ('^{}$'.format(re.escape(py_platform)), [wheel_targets[url[0]]])
            for py_platform, url in data.items()
        ]

        if deps:
            attrs['deps'] = deps

        if external_deps:
            attrs['platform_deps'].extend(
                self.format_platform_deps(
                    self.to_platform_deps(
                        [self.normalize_external_dep(d, lang_suffix='-py')
                         for d in external_deps]
                    )
                )
            )

        if tests:
            attrs['tests'] = tests

        yield Rule('python_library', attrs)

    def get_allowed_args(self):
        return {
            'version',
            'data',
            'deps',
            'external_deps',
            'tests',
        }

    def convert(self, base_path, version, data, **kwargs):
        """
        Entry point for converting python_wheel rules
        """
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        for rule in self.convert_rule(base_path, version, data, **kwargs):
            yield rule
