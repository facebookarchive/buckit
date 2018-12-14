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

import pipes

with allow_unsafe_import():  # noqa: magic
    import collections
    import os
    import re
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
compiled_wheel = re.compile('-cp[0-9]{2}-')

load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:python_typing.bzl", "gen_typing_config")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")


def get_url_basename(url):
    """ Urls will have an #md5 etag remove it and return the wheel name"""
    return os.path.basename(url).rsplit('#md5=')[0]


def remote_wheel(url, out, sha1, visibility):
    remote_file_name = out + '-remote'
    fb_native.remote_file(
        name=remote_file_name,
        visibility=get_visibility(visibility, remote_file_name),
        out=out,
        url=url,
        sha1=sha1,
    )
    return ":" + remote_file_name


def prebuilt_target(wheel, remote_target, visibility):
    fb_native.prebuilt_python_library(
        name=wheel,
        visibility=get_visibility(visibility, wheel),
        binary_src=remote_target,
    )
    return ":" + wheel


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
    msg = os.linesep.join(textwrap.wrap(msg, 79, subsequent_indent='  '))

    genrule_name = '{}-gen'.format(name)
    fb_native.cxx_genrule(
        name=genrule_name,
        visibility=get_visibility(visibility, genrule_name),
        out='out.cpp',
        cmd='echo {} 1>&2; false'.format(pipes.quote(msg)),
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
        name = os.path.basename(base_path)

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

        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['platform_deps'] = [
            ('{}$'.format(re.escape(py_platform)), [':' + version])
            for py_platform, version in sorted(platform_versions.items())
        ]
        # TODO: Figure out how to handle typing info from wheels
        if get_typing_config_target():
            gen_typing_config(attrs['name'], visibility=visibility)
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
            if url is None:
                continue
            if compiled_wheel.search(url):
                compiled = True
            orig_url, _, sha1 = url.rpartition('#sha1=')
            assert sha1, "There is no #sha1= tag on the end of URL: " + url
            # Opensource usage of this may have #md5 tags from pypi
            wheel = get_url_basename(orig_url)
            target_name = remote_wheel(url, wheel, sha1, visibility)
            target_name = prebuilt_target(wheel, target_name, visibility)
            wheel_targets[url] = target_name

        attrs = collections.OrderedDict()
        attrs['name'] = version
        if visibility is not None:
            attrs['visibility'] = visibility
        # Create the ability to override the platform that wheels use
        wheel_platform = read_config("python", "wheel_platform_override")

        # Use platform_deps to rely on the correct wheel target for
        # each platform
        attrs['platform_deps'] = [
            ('{}$'.format(re.escape(py_platform)), None if url is None else [wheel_targets[url]])
            for py_platform, url in sorted(platform_urls.items())
            # Some platforms just do not have wheels available. In this case, we remove
            # that platform from platform deps. You just won't get a whl on those
            # platforms. HOWEVER: Due to how platforms work in buck, if there's a
            # wheel_platform, we want to keep this platform. We keep it because a user
            # might still get something like 'gcc5-blah' as the buck native platform
            # even when we've overwritten all urls with say a mac specific url.
            # It sucks, and when select() and platform support is in buck and handled
            # properly by all rules, this will be wholly re-evaluated.
            if url or wheel_platform
        ]

        if wheel_platform:
            attrs['platform_deps'] = _override_wheels(attrs['platform_deps'], wheel_platform)

        # This is to work around how buck instantiates toolchains. Without this,
        # we don't always end up properly instantiating the c++ toolchains if
        # the compiler is a python script. T34675852
        cpp_genrule_name = version + "-genrule-hack"
        native.cxx_genrule(name = cpp_genrule_name, out="dummy", cmd="echo '' > $OUT")
        deps = (deps or []) + [":" + cpp_genrule_name]
        attrs['deps'] = deps

        if external_deps:
            if compiled:
                attrs['exclude_deps_from_merged_linking'] = True
            attrs['platform_deps'].extend(
                src_and_dep_helpers.format_platform_deps(
                    [src_and_dep_helpers.normalize_external_dep(d, lang_suffix='-py')
                     for d in external_deps]))

        if tests:
            attrs['tests'] = tests

        # TODO: Figure out how to handle typing info from wheels
        if get_typing_config_target():
            gen_typing_config(attrs['name'], visibility=visibility)
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


def _override_wheels(deps, wheel_platform):
    # For all deps, override the current wheel file with the one corresponding
    # to the specified wheel platform.

    # We're doing this because platforms in the list of deps are also re.escaped.
    wheel_platform = re.escape(wheel_platform)

    override_urls = None
    for platform, urls in deps:
        if wheel_platform in platform:
            override_urls = urls

    if not override_urls:
        return deps

    new_deps = []
    for platform, _ in deps:
        new_deps.append((platform, override_urls))

    return new_deps
