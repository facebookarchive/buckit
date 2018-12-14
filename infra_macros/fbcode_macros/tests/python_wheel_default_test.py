# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class PythonWheelDefaultTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:python_wheel_default.bzl", "python_wheel_default")
    ]

    @tests.utils.with_project()
    def test_python_wheel_default_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:python_wheel_default.bzl", "python_wheel_default")
            python_wheel_default(
                platform_versions = {
                    "py2-gcc-5-glibc-2.23": "1.11.5",
                    "py2-platform007": "1.11.5",
                },
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
