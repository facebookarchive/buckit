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


class ThirdPartyTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")]

    @tests.utils.with_project()
    def test_third_party_target_works_for_oss(self, root):
        self.addPathsConfig(
            root, third_party_root="", use_platforms_and_build_subdirs=False
        )

        commands = ['third_party.third_party_target("unused", "project", "rule")']
        expected = ["project//project:rule"]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_third_party_target_works(self, root):
        commands = ['third_party.third_party_target("platform", "project", "rule")']
        expected = ["//third-party-buck/platform/build/project:rule"]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_external_dep_target_fails_on_wrong_tuple_size(self, root):
        commands = [
            "third_party.external_dep_target("
            + '("foo", "bar", "baz", "other"), "platform")'
        ]
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands),
            "illegal external dependency ",
            "must have 1, 2, or 3 elements",
        )

    @tests.utils.with_project()
    def test_external_dep_target_fails_on_bad_raw_target(self, root):
        commands = [
            'third_party.external_dep_target({"not_a_string": "or_tuple"}, '
            '"platform")'
        ]
        self.assertFailureWithMessage(
            root.runUnitTests(self.includes, commands),
            "external dependency should be a tuple or string",
        )

    @tests.utils.with_project()
    def test_external_dep(self, root):
        commands = [
            'third_party.external_dep_target("foo", "platform")',
            'third_party.external_dep_target("foo", "platform", "-py")',
            'third_party.external_dep_target(("foo",), "platform")',
            'third_party.external_dep_target(("foo",), "platform", "-py")',
            'third_party.external_dep_target(("foo", "1.0"), "platform")',
            'third_party.external_dep_target(("foo", "1.0"), "platform", "-py")',
            'third_party.external_dep_target(("foo", "1.0", "bar"), "platform")',
            'third_party.external_dep_target(("foo", None, "bar"), "platform")',
        ]
        expected = [
            "//third-party-buck/platform/build/foo:foo",
            "//third-party-buck/platform/build/foo:foo-py",
            "//third-party-buck/platform/build/foo:foo",
            "//third-party-buck/platform/build/foo:foo-py",
            "//third-party-buck/platform/build/foo:foo",
            "//third-party-buck/platform/build/foo:foo-py",
            "//third-party-buck/platform/build/foo:bar",
            "//third-party-buck/platform/build/foo:bar",
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_external_dep_for_oss(self, root):
        self.addPathsConfig(root, "", False)
        commands = [
            'third_party.external_dep_target("foo", "platform")',
            'third_party.external_dep_target("foo", "platform", "-py")',
            'third_party.external_dep_target(("foo",), "platform")',
            'third_party.external_dep_target(("foo",), "platform", "-py")',
            'third_party.external_dep_target(("foo", "1.0"), "platform")',
            'third_party.external_dep_target(("foo", "1.0"), "platform", "-py")',
            'third_party.external_dep_target(("foo", "1.0", "bar"), "platform")',
            'third_party.external_dep_target(("foo", None, "bar"), "platform")',
        ]
        expected = [
            "foo//foo:foo",
            "foo//foo:foo-py",
            "foo//foo:foo",
            "foo//foo:foo-py",
            "foo//foo:foo",
            "foo//foo:foo-py",
            "foo//foo:bar",
            "foo//foo:bar",
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_replace_third_party_repo_works(self, root):
        self.addPathsConfig(root)
        self.addDummyThirdPartyConfig(root)
        self.addDummyPlatformOverrides(root)
        commands = [
            'third_party.replace_third_party_repo("foo bar", None)',
            'third_party.replace_third_party_repo("@/third-party-tools:foo:bar/baz", None)',
            'third_party.replace_third_party_repo("@/third-party-tools:foo:bar/baz", "gcc-5")',
            'third_party.replace_third_party_repo("@/third-party:foo:bar/baz", None)',
            'third_party.replace_third_party_repo("@/third-party:foo:bar/baz", "gcc-5")',
            'third_party.replace_third_party_repo("$(exe @/third-party-tools:clang:bin/clang) $(exe @/third-party:foo:bar)", None)',
        ]
        expected = [
            "foo bar",
            "//third-party-buck/default/tools/foo:bar/baz",
            "//third-party-buck/gcc-5/tools/foo:bar/baz",
            "//third-party-buck/default/build/foo:bar/baz",
            "//third-party-buck/gcc-5/build/foo:bar/baz",
            "$(exe //third-party-buck/default/tools/clang:bin/clang) $(exe //third-party-buck/default/build/foo:bar)",
        ]
        self.assertSuccess(
            root.runUnitTests(self.includes, commands, buckfile="foo/BUCK"), *expected
        )

    @tests.utils.with_project()
    def test_tool_paths_with_use_platforms_and_build_subdirs(self, root):
        self.addPathsConfig(root)
        self.addDummyThirdPartyConfig(root)
        self.addDummyPlatformOverrides(root)

        commands = [
            'third_party.get_build_path("gcc7")',
            'third_party.get_build_target_prefix("gcc7")',
            'third_party.get_tool_path("ld", "gcc7")',
            'third_party.get_tool_target("ld", "bin", "ldd", "gcc7")',
            'third_party.get_tool_bin_target("ld", "gcc7")',
        ]
        expected = [
            "third-party-buck/gcc7/build",
            "//third-party-buck/gcc7/build/",
            "third-party-buck/gcc7/tools/ld",
            "//third-party-buck/gcc7/tools/ld/bin:ldd",
            "//third-party-buck/gcc7/tools:ld/bin",
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_tool_paths_without_use_platforms_and_build_subdirs(self, root):
        self.addPathsConfig(root, use_platforms_and_build_subdirs=False)
        self.addDummyThirdPartyConfig(root)
        self.addDummyPlatformOverrides(root)

        commands = [
            'third_party.get_build_path("gcc7")',
            'third_party.get_build_target_prefix("gcc7")',
            'third_party.get_tool_path("ld", "gcc7")',
            'third_party.get_tool_target("ld", "bin", "ldd", "gcc7")',
            'third_party.get_tool_bin_target("ld", "gcc7")',
        ]
        expected = [
            "third-party-buck",
            "//third-party-buck/",
            "third-party-buck/ld",
            "ld//bin:ldd",
            "ld//ld:ld",
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_third_party_config_for_platform(self, root):
        commands = ['third_party.get_third_party_config_for_platform("gcc5")']
        expected = {
            "architecture": platform.machine(),
            "tools": {"projects": {"ghc": "8.0.2"}},
        }

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)

    @tests.utils.with_project()
    def test_is_tp2(self, root):
        commands = [
            'third_party.is_tp2("third-party-buck/foo")',
            'third_party.is_tp2("third-party-buck-thing/foo")',
            'third_party.is_tp2("foo/bar/baz")',
        ]
        expected = [True, False, False]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_is_tp2_src_dep(self, root):
        includes = self.includes + [
            ("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
        ]
        commands = [
            'third_party.is_tp2_src_dep("third-party-buck/foo.py")',
            'third_party.is_tp2_src_dep(target_utils.RootRuleTarget("foo/bar", "baz"))',
            'third_party.is_tp2_src_dep(target_utils.ThirdPartyRuleTarget("foo", "bar"))',
        ]
        expected = [False, False, True]

        self.assertSuccess(root.runUnitTests(includes, commands), *expected)

    @tests.utils.with_project()
    def test_get_tp2_platform(self, root):
        commands = [
            'third_party.get_tp2_platform("third-party-buck/some_plat/tools/foo")'
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), "some_plat")

    @tests.utils.with_project()
    def test_version_universe_matches_works(self, root):
        commands = [
            'third_party.get_version_universe([("python", "2.7")])',
            'third_party.get_version_universe([("python", "3.7")])',
            'third_party.get_version_universe([("python", "2.7"), ("openssl", "1.1.0")])',
            'third_party.get_version_universe([("python", "3.7"), ("openssl", "1.1.0")])',
        ]

        expected = [
            "openssl-1.0.2,python-2.7",
            "openssl-1.0.2,python-3.7",
            "openssl-1.1.0,python-2.7",
            "openssl-1.1.0,python-3.7",
        ]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
