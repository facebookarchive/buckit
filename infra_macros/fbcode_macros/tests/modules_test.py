# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import textwrap

import tests.utils


class ModulesTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:modules.bzl", "modules")]

    expected_cmd = (
        r"""set -euo pipefail\n"""
        r"""while test ! -r .projectid -a `pwd` != / ; do cd ..; done\n"""
        r"""args=()\n"""
        r"""args+=($(cxx))\n"""
        r"""args+=($(cxxppflags :foo-helper))\n"""
        r"""args+=($(cxxflags))\n"""
        r"""args+=(\'-fmodules\' \'-Rmodule-build\' \'-fimplicit-module-maps\' \'-fno-builtin-module-map\' \'-fno-implicit-modules\' \'-fmodules-cache-path=/DOES/NOT/EXIST\' \'-Xclang\' \'-fno-modules-global-index\' \'-Wnon-modular-include-in-module\' \'-Xclang\' \'-fno-absolute-module-directory\')\n"""
        r"""args+=(\"-Xclang\" \"-emit-module\")\n"""
        r"""args+=(\"-fmodule-name=\"\'bar\')\n"""
        r"""args+=(\"-x\" \"c++-header\")\n"""
        r"args+=(\"-Xclang\" \"-fno-validate-pch\")\n"
        r"""args+=(\"-I$SRCDIR/module_headers\")\n"""
        r"""args+=(\"$SRCDIR/module_headers/module.modulemap\")\n"""
        r"""args+=(\"-o\" \"-\")\n"""
        r"""for i in \"${!args[@]}\"; do\n"""
        r"""  args[$i]=${args[$i]//$PWD\\//}\n"""
        r"""done\n"""
        + (
            r"(\"${args[@]}\" 3>&1 1>&2 2>&3 3>&-) 2>\"$OUT\".tmp"
            + r" | >&2 sed \"s|${SRCDIR//$PWD\\//}/module_headers/|third-party-buck/something/|g\"\n"
        )
        + r'''mv -nT \"$OUT\".tmp \"$OUT\"'''
    )

    @tests.utils.with_project()
    def test_get_module_name(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                ['modules.get_module_name("fbcode", "base/path", "short-name")'],
            ),
            "fbcode//base/path:short-name",
        )

    @tests.utils.with_project()
    def test_get_module_map(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    'modules.get_module_map("name", {"header1.h": ["private"], "header2.h": {}})'
                ],
            ),
            textwrap.dedent(
                """\
                module "name" {
                  module "header1.h" {
                    private header "header1.h"
                    export *
                  }
                  module "header2.h" {
                    header "header2.h"
                    export *
                  }
                }
                """
            ),
        )

    @tests.utils.with_project(use_python=False, use_skylark=True)
    def test_gen_tp2_cpp_module_parses_skylark(self, root):
        root.addFile(
            "third-party-buck/something/BUCK",
            textwrap.dedent(
                """
            load("@fbcode_macros//build_defs:modules.bzl", "modules")
            modules.gen_tp2_cpp_module(
                name = "foo",
                module_name = "bar",
                headers = {"module.modulemap": "module.modulemap", "foo.h": "foo.cpp"},
                flags = ["-DFOO"],
                dependencies = [],
                platform = None,
                visibility = None,
            )
            """
            ),
        )
        expected = tests.utils.dedent(
            r"""
cxx_genrule(
  name = "foo",
  cmd = "{cmd}",
  out = "module.pcm",
  srcs = {{
    "module_headers/module.modulemap": "module.modulemap",
    "module_headers/foo.h": "foo.cpp",
  }},
)

cxx_library(
  name = "foo-helper",
  exported_preprocessor_flags = [
    "-DFOO",
  ],
  labels = [
    "generated",
  ],
  visibility = [
    "//third-party-buck/something:foo",
  ],
)
        """
        ).format(cmd=self.expected_cmd)
        result = root.runAudit(["third-party-buck/something/BUCK"])
        self.validateAudit({"third-party-buck/something/BUCK": expected}, result)

    @tests.utils.with_project(use_python=True, use_skylark=False)
    def test_gen_tp2_cpp_module_parses_py(self, root):
        root.addFile(
            "third-party-buck/something/BUCK",
            textwrap.dedent(
                """
            load("@fbcode_macros//build_defs:modules.bzl", "modules")
            modules.gen_tp2_cpp_module(
                name = "foo",
                module_name = "bar",
                headers = {"module.modulemap": "module.modulemap", "foo.h": "foo.cpp"},
                flags = ["-DFOO"],
                dependencies = [],
                platform = None,
                visibility = None,
            )
            """
            ),
        )

        expected = tests.utils.dedent(
            r"""
cxx_genrule(
  name = "foo",
  cmd = "{cmd}",
  out = "module.pcm",
  srcs = {{
    "module_headers/foo.h": "foo.cpp",
    "module_headers/module.modulemap": "module.modulemap",
  }},
)

cxx_library(
  name = "foo-helper",
  exported_preprocessor_flags = [
    "-DFOO",
  ],
  labels = [
    "generated",
  ],
  visibility = [
    "//third-party-buck/something:foo",
  ],
)
        """
        ).format(cmd=self.expected_cmd)
        result = root.runAudit(["third-party-buck/something/BUCK"])
        self.validateAudit({"third-party-buck/something/BUCK": expected}, result)
