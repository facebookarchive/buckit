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


class ThirdPartyTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:third_party.bzl", "third_party")]

    @tests.utils.with_project()
    def test_third_party_target_works_for_oss(self, root):
        self.addPathsConfig(
            root, third_party_root="", use_platforms_and_build_subdirs=False
        )

        commands = [
            'third_party.third_party_target("unused", "project", "rule")',
        ]
        expected = ["project//project:rule"]
        self.assertSuccess(
            root.run_unittests(self.includes, commands), *expected
        )

    @tests.utils.with_project()
    def test_third_party_target_works(self, root):
        self.addPathsConfig(root)
        commands = [
            'third_party.third_party_target("platform", "project", "rule")',
        ]
        expected = ["//third-party-buck/platform/build/project:rule"]
        self.assertSuccess(
            root.run_unittests(self.includes, commands), *expected
        )

    @tests.utils.with_project()
    def test_external_dep_target_fails_on_wrong_tuple_size(self, root):
        self.addPathsConfig(root)
        commands = [
            'third_party.external_dep_target(' +
            '("foo", "bar", "baz", "other"), "platform")',
        ]
        self.assertFailureWithMessage(
            root.run_unittests(self.includes, commands),
            'illegal external dependency ("foo", "bar", "baz", "other"): ' +
            'must have 1, 2, or 3 elements'
        )

    @tests.utils.with_project()
    def test_external_dep_target_fails_on_bad_raw_target(self, root):
        self.addPathsConfig(root)
        commands = [
            'third_party.external_dep_target({"not_a_string": "or_tuple"}, '
            '"platform")',
        ]
        self.assertFailureWithMessage(
            root.run_unittests(self.includes, commands),
            'external dependency should be a tuple or string'
        )

    @tests.utils.with_project()
    def test_external_dep(self, root):
        self.addPathsConfig(root)
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
            '//third-party-buck/platform/build/foo:foo',
            '//third-party-buck/platform/build/foo:foo-py',
            '//third-party-buck/platform/build/foo:foo',
            '//third-party-buck/platform/build/foo:foo-py',
            '//third-party-buck/platform/build/foo:foo',
            '//third-party-buck/platform/build/foo:foo-py',
            '//third-party-buck/platform/build/foo:bar',
            '//third-party-buck/platform/build/foo:bar',
        ]
        self.assertSuccess(
            root.run_unittests(self.includes, commands), *expected
        )

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
            'foo//foo:foo',
            'foo//foo:foo-py',
            'foo//foo:foo',
            'foo//foo:foo-py',
            'foo//foo:foo',
            'foo//foo:foo-py',
            'foo//foo:bar',
            'foo//foo:bar',
        ]
        self.assertSuccess(
            root.run_unittests(self.includes, commands), *expected
        )
