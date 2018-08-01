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

import tests.utils
from tests.utils import dedent


class BuildInfoTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:build_info.bzl", "build_info")]

    @tests.utils.with_project()
    def test_returns_empty_build_info_for_core_tools(self, root):
        root.updateBuckconfigWithDict({
            "build_info": {
                "epochtime": "1234",
                "host": "fb.example.com",
                "package_name": "some_package_app",
                "package_version": "1.0",
                "package_release": "5",
                "path": "/home/pjameson/some-repo",
                "revision": "5821da1851c676d3ad584a6a2670fa3e9d30baa4",
                "revision_epochtime": "2345",
                "time": "12:01:59",
                "time_iso8601": "2018-07-17T12:01:59Z",
                "upstream_revision": "0e427bf1c3b8e44ccb59554ae2ee610be6b5a054",
                "upstream_revision_epochtime": "3456",
                "user": "pjameson",
            },
        })
        root.project.cells["fbcode_macros"].writeFile(
            "build_defs/core_tools_targets.bzl",
            dedent(
                """
                load("@bazel_skylib//lib:new_sets.bzl", "sets")
                core_tools_targets = sets.make([
                    ("foo", "bar"),
                ])
                """))

        result = root.runUnitTests(
            self.includes,
            [
                'build_info.get_build_info(package_name(), "bar", "cpp_binary", "gcc5")',
            ],
            buckfile="foo/BUCK",
        )
        expected = [
            self.struct(
                build_mode="dev",
                rule="fbcode:foo:bar",
                platform="gcc5",
                rule_type="cpp_binary",
                epochtime=0,
                host="",
                package_name="",
                package_version="",
                package_release="",
                path="",
                revision="",
                revision_epochtime=0,
                time="",
                time_iso8601="",
                upstream_revision="",
                upstream_revision_epochtime=0,
                user="",
            )
        ]
        self.assertSuccess(result, *expected)

    @tests.utils.with_project()
    def test_returns_default_values_for_build_info_when_config_not_set(self, root):
        result = root.runUnitTests(
            self.includes,
            [
                'build_info.get_build_info(package_name(), "bar", "cpp_binary", "gcc5")',
            ],
            buckfile="foo/BUCK",
        )
        expected = [
            self.struct(
                build_mode="dev",
                rule="fbcode:foo:bar",
                platform="gcc5",
                rule_type="cpp_binary",
                epochtime=0,
                host="",
                package_name="",
                package_version="",
                package_release="",
                path="",
                revision="",
                revision_epochtime=0,
                time="",
                time_iso8601="",
                upstream_revision="",
                upstream_revision_epochtime=0,
                user="",
            )
        ]
        self.assertSuccess(result, *expected)

    @tests.utils.with_project()
    def test_returns_configured_values_for_build_info(self, root):
        root.updateBuckconfigWithDict({
            "build_info": {
                "epochtime": "1234",
                "host": "fb.example.com",
                "package_name": "some_packaged_app",
                "package_version": "1.0",
                "package_release": "5",
                "path": "/home/pjameson/some-repo",
                "revision": "5821da1851c676d3ad584a6a2670fa3e9d30baa4",
                "revision_epochtime": "2345",
                "time": "12:01:59",
                "time_iso8601": "2018-07-17T12:01:59Z",
                "upstream_revision": "0e427bf1c3b8e44ccb59554ae2ee610be6b5a054",
                "upstream_revision_epochtime": "3456",
                "user": "pjameson",
            },
        })
        result = root.runUnitTests(
            self.includes,
            [
                'build_info.get_build_info(package_name(), "bar", "cpp_binary", "gcc5")',
            ],
            buckfile="foo/BUCK",
        )
        expected = [
            self.struct(
                build_mode="dev",
                rule="fbcode:foo:bar",
                platform="gcc5",
                rule_type="cpp_binary",
                epochtime=1234,
                host="fb.example.com",
                package_name="some_packaged_app",
                package_version="1.0",
                package_release="5",
                path="/home/pjameson/some-repo",
                revision="5821da1851c676d3ad584a6a2670fa3e9d30baa4",
                revision_epochtime=2345,
                time="12:01:59",
                time_iso8601="2018-07-17T12:01:59Z",
                upstream_revision="0e427bf1c3b8e44ccb59554ae2ee610be6b5a054",
                upstream_revision_epochtime=3456,
                user="pjameson",
            )
        ]
        self.assertSuccess(result, *expected)


