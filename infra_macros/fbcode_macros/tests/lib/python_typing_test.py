# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class PythonTypingTest(tests.utils.TestCase):
    includes = [
        (
            "@fbcode_macros//build_defs/lib:python_typing.bzl",
            "get_typing_config_target",
            "gen_typing_config_attrs",
        )
    ]

    @tests.utils.with_project(run_buckd=True)
    def test_get_typing_config_target_obeys_buckconfig(self, root):
        self.assertSuccess(
            root.runUnitTests(
                includes=self.includes, statements=["get_typing_config_target()"]
            ),
            None,
        )

        root.updateBuckconfig("python", "typing_config", "//python:typing")
        self.assertSuccess(
            root.runUnitTests(
                includes=self.includes, statements=["get_typing_config_target()"]
            ),
            "//python:typing",
        )

    @tests.utils.with_project()
    def test_gen_typing_config_attrs_returns_expected_results(self, root):
        statements = [
            dedent(
                """
                gen_typing_config_attrs(
                    target_name="foobar",
                    base_path="foo.bar",
                    srcs=["test.py", "subdir/test2.py", ":rule"],
                    deps=[
                        "//other:dep", ":sibling",
                        "cross_cell//:foo", "//experimental:target"
                    ],
                    typing=True,
                    typing_options="--do --the --thing",
                    visibility=["//..."],
                )
            """
            ),
            dedent(
                """
                gen_typing_config_attrs(
                    target_name="foobar",
                )
            """
            ),
            dedent(
                """
                gen_typing_config_attrs(
                    target_name="foobar",
                    base_path="foo.bar",
                    srcs=["test.py", "subdir/test2.py", ":rule"],
                    deps=[
                        "//other:dep", ":sibling",
                        "cross_cell//:foo", "//experimental:target"
                    ],
                    typing=False,
                    typing_options="--do --the --thing",
                    visibility=["//..."],
                )
            """
            ),
        ]

        expected = [
            {
                "name": "foobar-typing",
                "visibility": ["PUBLIC"],
                "out": "root",
                "cmd": dedent(
                    """
                    mkdir -p "$OUT"
                    rsync -a "$(location //other:dep-typing)/" "$OUT/"
                    rsync -a "$(location :sibling-typing)/" "$OUT/"
                    mkdir -p `dirname $OUT/foo/bar/foobar`
                    {}
                """
                ).format(
                    '$(exe //python:typing) part --options="--do --the '
                    '--thing" $OUT/foo/bar/foobar foo/bar/test.py '
                    "foo/bar/subdir/test2.py foo/bar/:rule"
                ),
            },
            {
                "name": "foobar-typing",
                "out": "root",
                "cmd": 'mkdir -p "$OUT"',
                "visibility": ["PUBLIC"],
            },
            {
                "name": "foobar-typing",
                "visibility": ["PUBLIC"],
                "out": "root",
                "cmd": dedent(
                    """
                    mkdir -p "$OUT"
                    rsync -a "$(location //other:dep-typing)/" "$OUT/"
                    rsync -a "$(location :sibling-typing)/" "$OUT/"
                """
                ),
            },
        ]
        root.updateBuckconfig("python", "typing_config", "//python:typing")

        result = root.runUnitTests(self.includes, statements)
        self.assertSuccess(result, *expected)

    @tests.utils.with_project()
    def test_gen_typing_config_attrs_creates_genrules(self, root):
        root.updateBuckconfig("python", "typing_config", "//python:typing")
        root.addFile(
            "BUCK",
            dedent(
                """
        load("@fbcode_macros//build_defs/lib:python_typing.bzl",
            "gen_typing_config")

        gen_typing_config(
            target_name="foobar",
            base_path="foo.bar",
            srcs=["test.py", "subdir/test2.py", ":rule"],
            deps=[
                "//other:dep", ":sibling",
                "cross_cell//:foo", "//experimental:target"
            ],
            typing=True,
            typing_options="--do --the --thing",
            visibility=["//..."],
        )
        gen_typing_config(
            target_name="foobar2",
        )
        gen_typing_config(
            target_name="foobar3",
            base_path="foo.bar",
            srcs=["test.py", "subdir/test2.py", ":rule"],
            deps=[
                "//other:dep", ":sibling",
                "cross_cell//:foo", "//experimental:target"
            ],
            typing=False,
            typing_options="--do --the --thing",
            visibility=["//..."],
        )
        """
            ),
        )

        expected = dedent(
            r"""
            genrule(
              name = "foobar-typing",
              cmd = "{cmd1}",
              labels = [
                "is_fully_translated",
              ],
              out = "root",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar2-typing",
              cmd = "mkdir -p \"$OUT\"",
              labels = [
                "is_fully_translated",
              ],
              out = "root",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar3-typing",
              cmd = "{cmd3}",
              labels = [
                "is_fully_translated",
              ],
              out = "root",
              visibility = [
                "PUBLIC",
              ],
            )
            """
        ).format(
            cmd1=(
                r"mkdir -p \"$OUT\"\nrsync -a \"$(location "
                r"//other:dep-typing)/\" \"$OUT/\"\nrsync -a \"$(location "
                r":sibling-typing)/\" \"$OUT/\"\nmkdir -p `dirname "
                r"$OUT/foo/bar/foobar`\n$(exe //python:typing) part "
                r"--options=\"--do --the --thing\" $OUT/foo/bar/foobar "
                r"foo/bar/test.py foo/bar/subdir/test2.py foo/bar/:rule"
            ),
            cmd3=(
                r"mkdir -p \"$OUT\"\nrsync -a \"$(location "
                r"//other:dep-typing)/\" \"$OUT/\"\nrsync -a "
                r"\"$(location :sibling-typing)/\" \"$OUT/\""
            ),
        )

        result = root.runAudit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)
