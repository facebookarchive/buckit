# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class YaccTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_yacc_parses(self, root):
        buckfile = "testing/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:yacc.bzl", "yacc")
        yacc(
            name = "some_yacc",
            yacc_flags = ["--skeleton=lalr1.cc"],
            yacc_src = "file.yy",
            platform = "gcc5",
            visibility = ["PUBLIC"],
        )
        """
            ),
        )

        cmd = (
            r"""mkdir -p $OUT && """
            r"""$(exe //third-party-buck/gcc5/tools/bison:bison) \'-y\' \'-d\' \'--skeleton=lalr1.cc\' -o \"$OUT/\"\'file.yy\'.c $SRCS && """
            r"""sed -i -e \'s|\'\"$SRCS\"\'|\'\'testing/file.yy\'\'|g\'  -e \'s|YY_YY_.*_INCLUDED|YY_YY_TESTING_FILE_YY_H_INCLUDED|g\'  \"$OUT/\"\'file.yy\'.c \"$OUT/\"\'file.yy\'.h && """
            r"""sed -i -e \'s|\\b\'\'file.yy\'\'\\.c\\b|\'\'file.yy\'\'.cc|g\'  -e \'s|\'\"$OUT/\"\'file.yy\'\'\\.cc\\b|\'\'buck-out/gen/testing/file.yy.cc/file.yy.cc\'\'|g\'  \"$OUT/\"\'file.yy\'.c && """
            r"""sed -i -e \'s|\'\"$OUT/\"\'file.yy\'\'\\.h\\b|\'\'buck-out/gen/testing/file.yy.h/file.yy.h\'\'|g\' \"$OUT/\"\'file.yy\'.h && """
            r"""mv \"$OUT/\"\'file.yy\'.c \"$OUT/\"\'file.yy\'.cc && """
            r"""sed -i -e \'s|#include \"\'\'file.yy\'.h\'\"|#include \"\'testing/\'file.yy\'.h\'\"|g\'  \"$OUT/\"\'file.yy\'.cc && """
            r"""sed -i -e \'s|#\\(.*\\)YY_YY_[A-Z0-9_]*_FBCODE_|#\\1YY_YY_FBCODE_|g\'  -e \'s|#line \\([0-9]*\\) \"/.*/fbcode/|#line \\1 \"fbcode/|g\'  -e \'s|\\\\file /.*/fbcode/|\\\\file fbcode/|g\'  \"$OUT/\"stack.hh"""
        )
        expected = {
            buckfile: dedent(
                r"""
genrule(
  name = "some_yacc=file.yy",
  cmd = "{cmd}",
  labels = [
    "is_fully_translated",
  ],
  out = "file.yy.d",
  srcs = [
    "file.yy",
  ],
)

genrule(
  name = "some_yacc=file.yy.cc",
  cmd = "mkdir -p `dirname \"$OUT\"` && cp -rlTP \"$(location :some_yacc=file.yy)/file.yy.cc\" \"$OUT\"",
  labels = [
    "is_fully_translated",
  ],
  out = "file.yy.cc",
  visibility = [
    "PUBLIC",
  ],
)

genrule(
  name = "some_yacc=file.yy.h",
  cmd = "mkdir -p `dirname \"$OUT\"` && cp -rlTP \"$(location :some_yacc=file.yy)/file.yy.h\" \"$OUT\"",
  labels = [
    "is_fully_translated",
  ],
  out = "file.yy.h",
  visibility = [
    "PUBLIC",
  ],
)

genrule(
  name = "some_yacc=stack.hh",
  cmd = "mkdir -p `dirname \"$OUT\"` && cp -rlTP \"$(location :some_yacc=file.yy)/stack.hh\" \"$OUT\"",
  labels = [
    "is_fully_translated",
  ],
  out = "stack.hh",
  visibility = [
    "PUBLIC",
  ],
)
                """
            ).format(cmd=cmd)
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
