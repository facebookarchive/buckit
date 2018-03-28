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
load("@fbcode_macros//build_defs:python_typing.bzl",
     "get_typing_config_target")
compiled_wheel = re.compile('-cp[0-9]{2}-')


def get_url_basename(url):
    """ Urls will have an #md5 etag remove it and return the wheel name"""
    return os.path.basename(url).rsplit('#md5=')[0]


def gen_remote_wheel(url, out, sha1, visibility):
    attrs = collections.OrderedDict()
    attrs['name'] = out + '-remote'
    if visibility is not None:
        attrs['visibility'] = visibility
    attrs['out'] = out
    attrs['url'] = url
    attrs['sha1'] = sha1
    return Rule('remote_file', attrs)


def gen_prebuilt_target(wheel, remote_target, visibility):
    attrs = collections.OrderedDict()
    attrs['name'] = wheel
    if visibility is not None:
        attrs['visibility'] = visibility
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
            'platform_versions'
        }

    def convert_rule(self, base_path, platform_versions, visibility):
        name = os.path.basename(base_path)

        # If there is no default for either py2 or py3 for the given platform
        # Then we should fail to return a rule, instead of silently building
        # but not actually providing the wheel.  To do this, emit and add
        # platform deps onto "error" rules that will fail at build time.
        platform_versions = collections.OrderedDict(platform_versions)
        for platform in self.get_platforms():
            py2_plat = self.get_py2_platform(platform)
            py3_plat = self.get_py3_platform(platform)
            present_for_any_python_version = (
                py2_plat in platform_versions or py3_plat in platform_versions
            )
            if not present_for_any_python_version:
                msg = (
                    '{}: wheel does not exist for platform "{}"'
                    .format(name, platform))
                error_name = '{}-{}-error'.format(name, platform)
                for rule in self.create_error_rules(error_name, msg):
                    yield rule
                platform_versions[py2_plat] = error_name
                platform_versions[py3_plat] = error_name

        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['platform_deps'] = [
            ('^{}$'.format(re.escape(py_platform)), [':' + version])
            for py_platform, version in sorted(platform_versions.items())
        ]
        # TODO: Figure out how to handle typing info from wheels
        if get_typing_config_target():
            yield self.gen_typing_config(attrs['name'], visibility=visibility)
        yield Rule('python_library', attrs)

    def convert(self, base_path, platform_versions, visibility=None):
        """
        Entry point for converting python_wheel rules
        """
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        for rule in self.convert_rule(base_path, platform_versions, visibility=visibility):
            yield rule


class PyWheel(base.Converter):
    def get_fbconfig_rule_type(self):
        return 'python_wheel'

    def convert_rule(
        self,
        base_path,
        version,
        platform_urls,  # Dict[str, str]   # platform -> url
        deps=(),
        external_deps=(),
        tests=(),
        visibility=None,
    ):
        # We don't need duplicate targets if we have multiple usage of URLs
        urls = set(platform_urls.values())
        wheel_targets = {}  # Dict[str, str]      # url -> prebuilt_target_name

        compiled = False
        # Setup all the remote_file and prebuilt_python_library targets
        # urls have #sha1=<sha1> at the end.
        for url in urls:
            if compiled_wheel.search(url):
                compiled = True
            orig_url, _, sha1 = url.rpartition('#sha1=')
            assert sha1, "There is no #sha1= tag on the end of URL: " + url
            # Opensource usage of this may have #md5 tags from pypi
            wheel = get_url_basename(orig_url)
            rule = gen_remote_wheel(url, wheel, sha1, visibility)
            yield rule
            rule = gen_prebuilt_target(wheel, rule.target_name, visibility)
            yield rule
            wheel_targets[url] = rule.target_name

        attrs = collections.OrderedDict()
        attrs['name'] = version
        if visibility is not None:
            attrs['visibility'] = visibility
        # Use platform_deps to rely on the correct wheel target for
        # each platform
        attrs['platform_deps'] = [
            ('^{}$'.format(re.escape(py_platform)), [wheel_targets[url]])
            for py_platform, url in sorted(platform_urls.items())
        ]

        if deps:
            attrs['deps'] = deps

        if external_deps:
            if compiled:
                attrs['exclude_deps_from_merged_linking'] = True
            attrs['platform_deps'].extend(
                self.format_platform_deps(
                    self.to_platform_param(
                        [self.normalize_external_dep(d, lang_suffix='-py')
                         for d in external_deps]
                    )
                )
            )

        if tests:
            attrs['tests'] = tests

        # TODO: Figure out how to handle typing info from wheels
        if get_typing_config_target():
            yield self.gen_typing_config(attrs['name'], visibility=visibility)
        yield Rule('python_library', attrs)

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
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        for rule in self.convert_rule(base_path, version, platform_urls, visibility=visibility, **kwargs):
            yield rule
