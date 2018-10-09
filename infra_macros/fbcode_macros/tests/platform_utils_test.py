# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import platform

import tests.utils
from tests.utils import dedent


class PlatformTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")]

    current_arch = platform.machine()
    other_arch = "x86_64" if current_arch == "aarch64" else "aarch64"

    third_party_config = dedent(
        """\
            third_party_config = {{
                "platforms": {{
                    "gcc5": {{
                        "architecture": "{current_arch}",
                    }},
                    "gcc6": {{
                        "architecture": "{current_arch}",
                    }},
                    "gcc7": {{
                        "architecture": "{current_arch}",
                    }},
                    "gcc5-other": {{
                        "architecture": "{other_arch}",
                    }},
                }},
            }}
        """.format(
            current_arch=current_arch, other_arch=other_arch
        )
    )

    @tests.utils.with_project()
    def test_transform_platform_overrides(self, root):
        # This should be a load time error
        platform_overrides = dedent(
            """\
            platform_overrides = {
                "fbcode": {
                    "foo/bar": ["gcc5", "gcc5-other"],
                    "foo": ["gcc7"],
                },
            }
            """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )
        expected = {
            "fbcode": {
                "foo/bar": {self.other_arch: "gcc5-other", self.current_arch: "gcc5"},
                "foo": {self.current_arch: "gcc7"},
            }
        }
        result = root.runUnitTests(
            self.includes, ["platform_utils.get_platform_overrides()"]
        )
        self.assertSuccess(result, expected)

    @tests.utils.with_project()
    def test_transform_platform_overrides_fails_with_invalid_platform(self, root):
        # This should be a load time error
        platform_overrides = dedent(
            """\
            platform_overrides = {
                "fbcode": {
                    "foo/bar": ["gcc5", "invalid-platform"],
                },
            }
            """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )

        result = root.runUnitTests(
            self.includes, ["platform_utils.get_platform_overrides()"]
        )
        self.assertFailureWithMessage(
            result,
            "Path foo/bar has invalid platform invalid-platform. Must be one "
            "of gcc5, gcc5-other, gcc6, gcc7",
        )

    @tests.utils.with_project()
    def test_transform_platform_overrides_fails_with_duplicate_platforms_for_arch(
        self, root
    ):
        # This should be a load time error
        platform_overrides = dedent(
            """\
            platform_overrides = {
                "fbcode": {
                    "foo/bar": ["gcc5", "gcc7"],
                },
            }
            """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )

        result = root.runUnitTests(
            self.includes, ["platform_utils.get_platform_overrides()"]
        )
        self.assertFailureWithMessage(
            result,
            "Path foo/bar has both platform gcc5 and gcc7 for architecture %s"
            % self.current_arch,
        )

    @tests.utils.with_project()
    def test_get_platform_fails_when_platform_required(self, root):
        statements = ['platform_utils.get_platform_for_base_path("blah")']
        root.updateBuckconfig("fbcode", "require_platform", "true")

        results = root.runUnitTests(self.includes, statements)
        self.assertFailureWithMessage(
            results,
            "Cannot find fbcode platform to use for architecture {}".format(
                self.current_arch
            ),
        )

    @tests.utils.with_project()
    def test_get_platform_default_when_platform_not_required(self, root):
        statements = ['platform_utils.get_platform_for_base_path("blah")']

        results = root.runUnitTests(self.includes, statements)
        self.assertSuccess(results, "default")

    @tests.utils.with_project()
    def test_base_name_gets_correct_platform_for_various_directories_and_archs(
        self, root
    ):
        platform_overrides = dedent(
            """\
            platform_overrides = {"fbcode": {
                "foo/bar": ["gcc5-other", "gcc5"],
                "foo/bar-other": ["gcc5-other"],
                "foo": ["gcc6"],
                "": ["gcc7"],
            }}
        """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )
        statements = [
            'platform_utils.get_platform_for_base_path("foo/bar")',
            'platform_utils.get_platform_for_base_path("foo/bar-other")',
            'platform_utils.get_platform_for_base_path("foo/baz")',
            'platform_utils.get_platform_for_base_path("foo")',
            'platform_utils.get_platform_for_base_path("foobar")',
        ]
        result = root.runUnitTests(self.includes, statements)
        self.assertSuccess(result, "gcc5", "gcc6", "gcc6", "gcc6", "gcc7")

    @tests.utils.with_project()
    def test_gets_correct_platform_for_various_directories_and_archs(self, root):
        platform_overrides = dedent(
            """\
            platform_overrides = {"fbcode": {
                "foo/bar": ["gcc5-other", "gcc5"],
                "foo/bar-other": ["gcc5-other"],
                "foo": ["gcc6"],
                "": ["gcc7"],
            }}
        """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )
        statements = ["platform_utils.get_platform_for_current_buildfile()"]
        result1 = root.runUnitTests(self.includes, statements, buckfile="foo/bar/BUCK")
        result2 = root.runUnitTests(
            self.includes, statements, buckfile="foo/bar-other/BUCK"
        )
        result3 = root.runUnitTests(self.includes, statements, buckfile="foo/baz/BUCK")
        result4 = root.runUnitTests(self.includes, statements, buckfile="foo/BUCK")
        result5 = root.runUnitTests(self.includes, statements, buckfile="foobar/BUCK")

        self.assertSuccess(result1, "gcc5")
        self.assertSuccess(result2, "gcc6")
        self.assertSuccess(result3, "gcc6")
        self.assertSuccess(result4, "gcc6")
        self.assertSuccess(result5, "gcc7")

    @tests.utils.with_project()
    def test_returns_platform_override_if_set(self, root):
        platform_overrides = dedent(
            """\
            platform_overrides = {"fbcode": {
                "foo/bar": ["gcc5-other", "gcc5"],
                "": ["gcc7"],
            }}
        """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )
        root.updateBuckconfig("fbcode", "platform", "gcc8")

        statements = [
            'platform_utils.get_platform_for_base_path("foo/bar")',
            'platform_utils.get_platform_for_base_path("foobar")',
        ]
        result = root.runUnitTests(self.includes, statements)
        self.assertSuccess(result, "gcc8", "gcc8")

    @tests.utils.with_project()
    def test_helper_util_runs_properly(self, root):
        platform_overrides = dedent(
            """\
            platform_overrides = {"fbcode": {
                "foo/bar": ["gcc5-other", "gcc5"],
                "foo/bar-other": ["gcc5-other"],
                "foo": ["gcc6"],
                "": ["gcc7"],
            }}
        """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )

        result = root.run(
            [
                "buck",
                "run",
                "fbcode_macros//tools:get_platform",
                "foo/bar",
                "foo/bar-other",
                "foo/baz",
                "foo",
                "foobar",
            ],
            {},
            {},
        )
        self.assertSuccess(result)
        expected = (
            dedent(
                """
            foo/bar:gcc5
            foo/bar-other:gcc6
            foo/baz:gcc6
            foo:gcc6
            foobar:gcc7
            """
            )
            + "\n"
        )
        self.assertEqual(expected, result.stdout)

    @tests.utils.with_project()
    def test_get_platform_architecture(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes, ['platform_utils.get_platform_architecture("gcc7")']
            ),
            platform.machine(),
        )

    @tests.utils.with_project()
    def test_get_all_platforms(self, root):
        result = root.runUnitTests(
            self.includes, ["platform_utils.get_all_platforms()"]
        )
        self.assertSuccess(result)
        self.assertEquals(
            ["default", "gcc5", "gcc5-other", "gcc6", "gcc7"],
            sorted(result.debug_lines[0]),
        )

    @tests.utils.with_project()
    def test_get_platforms_for_host_architecture(self, root):
        result = root.runUnitTests(
            self.includes,
            [
                "platform_utils.get_platforms_for_host_architecture()",
            ],
        )
        self.assertSuccess(result)
        self.assertEquals(
            ["default", "gcc5", "gcc6", "gcc7"], sorted(result.debug_lines[0])
        )

    @tests.utils.with_project()
    def test_get_platforms_for_architecture(self, root):
        result = root.runUnitTests(
            self.includes,
            [
                'platform_utils.get_platforms_for_architecture("{}")'.format(
                    self.other_arch
                )
            ],
        )
        self.assertSuccess(result, ["gcc5-other"])
