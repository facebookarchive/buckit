# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class LexTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_lex_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:lex.bzl", "lex")
            lex(
                name = "parser",
                lex_flags = ["-i"],
                lex_src = "token.ll",
                platform = "gcc5",
                visibility = [
                    "PUBLIC",
                ],
            )
            """
            ),
        )

        expected = {
            "BUCK": dedent(
                r"""
genrule(
  name = "parser=token.ll",
  cmd = "mkdir -p \"$OUT\" && $(exe //third-party-buck/gcc5/tools/flex:flex) \'-i\' -o$OUT/\'token.ll.cc\' --header-file=$OUT/\'token.ll.h\' $SRCS && perl -pi -e \'s!\\Q\'\"\\$(realpath \"$GEN_DIR/../..\")\"\'/\\E!!\'  \"$OUT\"/\'token.ll.cc\' \"$OUT\"/\'token.ll.h\'",
  out = "token.ll.d",
  srcs = [
    "token.ll",
  ],
  visibility = [
    "PUBLIC",
  ],
)

genrule(
  name = "parser=token.ll.cc",
  cmd = "mkdir -p `dirname \"$OUT\"` && cp -rlTP \"$(location :parser=token.ll)/token.ll.cc\" \"$OUT\"",
  out = "token.ll.cc",
  visibility = [
    "PUBLIC",
  ],
)

genrule(
  name = "parser=token.ll.h",
  cmd = "mkdir -p `dirname \"$OUT\"` && cp -rlTP \"$(location :parser=token.ll)/token.ll.h\" \"$OUT\"",
  out = "token.ll.h",
  visibility = [
    "PUBLIC",
  ],
)
                """
            )
        }

        self.validateAudit(expected, root.runAudit(["BUCK"]))
