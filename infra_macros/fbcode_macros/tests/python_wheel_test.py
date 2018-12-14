# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class PythonWheelTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:python_wheel.bzl", "python_wheel")]

    @tests.utils.with_project()
    def test_python_wheel_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:python_wheel.bzl", "python_wheel")
            python_wheel(
                platform_urls = {
                    "py2-gcc-5-glibc-2.23": "https://foo/cffi-1.11.5-cp27-cp27mu-gcc_5_glibc_2_23.whl#sha1=719636a0c45e3845c3aa11cac3f9eb4f31b9f36d",
                    "py2-platform007": "https://foo/cffi-1.11.5-cp27-cp27mu-platform007.whl#sha1=0300087061371f6d9d1bcc66569fa4f43128a336",
                },
                version = "1.11.5",
                deps = [
                    "//python/wheel/pycparser:pycparser",
                ],
                external_deps = [
                    ("libffi", None, "ffi"),
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
