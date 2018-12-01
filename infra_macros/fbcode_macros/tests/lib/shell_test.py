# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import shlex

import tests.utils


class ShellTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:shell.bzl", "shell")]

    @tests.utils.with_project()
    def test_split_works_like_shlex_split(self, root):
        test_strings = [
            r"",
            r"FOO BAR",
            " foo \t\nbar\n baz",
            r'foo -D"bar"',
            r'foo -D"\"something quoted\"" last\ string',
            r'foo -D"\n contains backslash still" ',
            r"""foo -D'something something \"dark side\"'""",
            r"""-DFOO   -D"\ B'A'R=\"something here\""'something" else' -D\ BAZ -D\\some""",
            r'''-DFOO -DBAR="baz \"\\\"lots of quotes\\\"\""''',
        ]

        commands = ["shell.split(%r)" % s.encode("ascii") for s in test_strings]
        expected = [shlex.split(s) for s in test_strings]

        result = root.runUnitTests(self.includes, commands)

        self.assertSuccess(result)
        self.assertEqual(
            expected, [[x.encode("utf-8") for x in line] for line in result.debug_lines]
        )
