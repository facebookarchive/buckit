# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class MissingTp2ProjectTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_prints_error_message(self, root):
        buckfile = dedent(
            r"""
            load(
                "@fbcode_macros//build_defs:missing_tp2_project.bzl",
                "missing_tp2_project",
            )
            missing_tp2_project(
                name="foo_some_long_project_name",
                project="really_long_project",
                platform="random_platform",
            )
            cxx_binary(
                name = "main",
                srcs = ["main.cpp"],
                deps = [":foo_some_long_project_name"],
            )
            """
        )
        root.addFile("BUCK", buckfile)
        root.addFile("main.cpp", "int main() { return 0; }")
        result = root.run(["buck", "build", "//:main"], {}, {})

        self.assertFailureWithMessage(
            result,
            (
                "ERROR: foo_some_long_project_name: project "
                + '"really_long_project" does\n       not exist for '
                + 'platform "random_platform"'
            ),
        )
        self.assertFalse(
            "java.nio.file.NoSuchFileException" in result.stderr,
            msg="Found NoSuchFileException in %s" % result.stderr,
        )
