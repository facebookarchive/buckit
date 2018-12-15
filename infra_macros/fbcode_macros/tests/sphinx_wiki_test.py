# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class SphinxWikiTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:sphinx_wiki.bzl", "sphinx_wiki")]

    @tests.utils.with_project()
    def test_sphinx_wiki_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:sphinx_wiki.bzl", "sphinx_wiki")
            sphinx_wiki(
                name = "docs",
                srcs = [
                    "README.rst",
                ],
                config = {
                    "conf.py": {
                        "default_role": "fb:wut",  #T32942441
                        "extlinks": {
                            "sphinx-doc": "http://www.sphinx-doc.org/en/master/%s;",
                        },
                    },
                    "sphinx-build": {
                        "treat_warnings_as_errors": True,
                    },
                },
                genrule_srcs = {
                    "//fbsphinx:commands_documentor": "guide/commands",
                    "//fbsphinx:extensions_documentor": "guide/reStructuredText",
                },
                python_library_deps = [
                    "//fbsphinx:lib",
                    "//fbsphinx:bin",
                ],
                wiki_root_path = "fbsphinx",
            )
            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))
