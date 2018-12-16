# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import textwrap

import tests.utils


class PlatformTest(tests.utils.TestCase):

    includes = [
        (
            "@fbcode_macros//build_defs/lib:fbcode_cxx_platforms.bzl",
            "fbcode_cxx_platforms",
        ),
        ("@fbcode_macros//build_defs/lib:virtual_cells.bzl", "virtual_cells"),
        ("@fbcode_macros//build_defs/lib:rule_target_types.bzl", "rule_target_types"),
    ]

    @tests.utils.with_project()
    def test_build_platforms(self, root):
        config = {"foo": {"architecture": "blah"}}
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    "fbcode_cxx_platforms.build_platforms({}, virtual_cells = False)".format(
                        json.dumps(config)
                    )
                ],
            ),
            [
                self.struct(
                    alias="foo",
                    compiler_family="clang",
                    host_arch="blah",
                    host_os="linux",
                    name="foo-clang",
                    target_arch="blah",
                    target_os="linux",
                    virtual_cells=None,
                ),
                self.struct(
                    alias="foo",
                    compiler_family="gcc",
                    host_arch="blah",
                    host_os="linux",
                    name="foo-gcc",
                    target_arch="blah",
                    target_os="linux",
                    virtual_cells=None,
                ),
            ],
        )

    @tests.utils.with_project()
    def test_build_virtual_cells(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    textwrap.dedent(
                        """\
                        virtual_cells.translate_target(
                            fbcode_cxx_platforms.build_tp2_virtual_cells("default"),
                            rule_target_types.ThirdPartyRuleTarget("foo", "bar"),
                        )
                        """
                    ),
                    textwrap.dedent(
                        """\
                        virtual_cells.translate_target(
                            fbcode_cxx_platforms.build_tp2_virtual_cells("default"),
                            rule_target_types.ThirdPartyToolRuleTarget("foo", "bar"),
                        )
                        """
                    ),
                ],
            ),
            self.struct(
                base_path="third-party-buck/default/build/foo",
                name="bar",
                repo="fbcode",
            ),
            self.struct(
                base_path="third-party-buck/default/tools/foo",
                name="bar",
                repo="fbcode",
            ),
        )
