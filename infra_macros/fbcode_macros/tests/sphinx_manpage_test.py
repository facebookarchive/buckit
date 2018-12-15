# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class SphinxManpageTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:sphinx_manpage.bzl", "sphinx_manpage")]

    @tests.utils.with_project()
    def test_sphinx_manpage_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:sphinx_manpage.bzl", "sphinx_manpage")
            sphinx_manpage(
                name = "fbsphinx_manpage",
                srcs = ["guide/commands/README.rst"],
                author = "Fbsphinx",
                description = "Tool for invoking fbSphinx commands, like build and preview",
                genrule_srcs = {
                    "//fbsphinx:commands_documentor": "guide/commands",
                },
                manpage_name = "fbsphinx",
                python_library_deps = [
                    "//fbsphinx:bin",
                ],
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
