# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class GoBinaryTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_go_binary_parses(self, root):
        buckfile = "testing/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:go_binary.bzl", "go_binary")
        go_binary(
            name = "foo",
            deps = [":otherArtifact"],
            licenses = ["LICENSE"],
            visibility = None,
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                go_binary(
                  name = "foo",
                  licenses = [
                    "LICENSE",
                  ],
                  platform = "default-gcc",
                  deps = [
                    "//testing:otherArtifact",
                  ],
                  visibility = [
                    "PUBLIC",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
