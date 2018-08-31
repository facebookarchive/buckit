# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import json

import tests.utils
from tests.utils import dedent


class BuildModeTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:build_mode.bzl", "build_mode"),
        ("@fbcode_macros//build_defs:create_build_mode.bzl", "create_build_mode"),
        ("@fbcode_macros//build_defs:create_build_mode.bzl", "extend_build_mode"),
    ]

    def _create_mode_struct(
            self,
            aspp_flags=(),
            cpp_flags=(),
            cxxpp_flags=(),
            c_flags=(),
            cxx_flags=(),
            ld_flags=(),
            clang_flags=(),
            gcc_flags=(),
            java_flags=(),
            dmd_flags=(),
            gdc_flags=(),
            ldc_flags=(),
            par_flags=(),
            ghc_flags=(),
            asan_options=(),
            ubsan_options=(),
            tsan_options=(),
            lsan_suppressions=(),
            cxx_modules=None,
            compiler=None):
        return self.struct(
            aspp_flags=aspp_flags,
            cpp_flags=cpp_flags,
            cxxpp_flags=cxxpp_flags,
            c_flags=c_flags,
            cxx_flags=cxx_flags,
            ld_flags=ld_flags,
            clang_flags=clang_flags,
            gcc_flags=gcc_flags,
            java_flags=java_flags,
            dmd_flags=dmd_flags,
            gdc_flags=gdc_flags,
            ldc_flags=ldc_flags,
            par_flags=par_flags,
            ghc_flags=ghc_flags,
            asan_options=asan_options,
            ubsan_options=ubsan_options,
            tsan_options=tsan_options,
            lsan_suppressions=lsan_suppressions,
            cxx_modules=cxx_modules,
            compiler=compiler)

    @tests.utils.with_project()
    def test_creates_proper_build_modes(self, root):
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl",
            "build_mode_overrides = {}")

        statements = [
            'create_build_mode(aspp_flags=["-DFLAG"])',
            'create_build_mode(c_flags=["-DFLAG"])',
            'create_build_mode(clang_flags=["-DFLAG"])',
            'create_build_mode(cpp_flags=["-DFLAG"])',
            'create_build_mode(cxx_flags=["-DFLAG"])',
            'create_build_mode(cxxpp_flags=["-DFLAG"])',
            'create_build_mode(dmd_flags=["-DFLAG"])',
            'create_build_mode(gcc_flags=["-DFLAG"])',
            'create_build_mode(gdc_flags=["-DFLAG"])',
            'create_build_mode(ghc_flags=["-DFLAG"])',
            'create_build_mode(java_flags=["-DFLAG"])',
            'create_build_mode(ldc_flags=["-DFLAG"])',
            'create_build_mode(ld_flags=["-DFLAG"])',
            'create_build_mode(par_flags=["-DFLAG"])',
            'create_build_mode(asan_options={"a":"1"})',
            'create_build_mode(ubsan_options={"b":"2"})',
            'create_build_mode(tsan_options={"c":"3"})',
            'create_build_mode(lsan_suppressions=["a/b/c"])',
            'create_build_mode(cxx_modules=True)',
        ]
        expected = [
            self._create_mode_struct(aspp_flags=["-DFLAG"]),
            self._create_mode_struct(c_flags=["-DFLAG"]),
            self._create_mode_struct(clang_flags=["-DFLAG"]),
            self._create_mode_struct(cpp_flags=["-DFLAG"]),
            self._create_mode_struct(cxx_flags=["-DFLAG"]),
            self._create_mode_struct(cxxpp_flags=["-DFLAG"]),
            self._create_mode_struct(dmd_flags=["-DFLAG"]),
            self._create_mode_struct(gcc_flags=["-DFLAG"]),
            self._create_mode_struct(gdc_flags=["-DFLAG"]),
            self._create_mode_struct(ghc_flags=["-DFLAG"]),
            self._create_mode_struct(java_flags=["-DFLAG"]),
            self._create_mode_struct(ldc_flags=["-DFLAG"]),
            self._create_mode_struct(ld_flags=["-DFLAG"]),
            self._create_mode_struct(par_flags=["-DFLAG"]),
            self._create_mode_struct(asan_options={"a":"1"}),
            self._create_mode_struct(ubsan_options={"b":"2"}),
            self._create_mode_struct(tsan_options={"c":"3"}),
            self._create_mode_struct(lsan_suppressions=["a/b/c"]),
            self._create_mode_struct(cxx_modules=True),
        ]
        result = root.runUnitTests(self.includes, statements)
        self.assertSuccess(result, *expected)

    @tests.utils.with_project()
    def test_extends_proper_build_modes(self, root):
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl",
            "build_mode_overrides = {}")

        statements = [
            'extend_build_mode(create_build_mode(aspp_flags=["-DFLAG"]), aspp_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(c_flags=("-DFLAG",)), c_flags=("-DFLAG_TWO",))',
            'extend_build_mode(create_build_mode(clang_flags=["-DFLAG"]), clang_flags=("-DFLAG_TWO",))',
            'extend_build_mode(create_build_mode(cpp_flags=("-DFLAG",)), cpp_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(cxx_flags=["-DFLAG"]), cxx_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(cxxpp_flags=["-DFLAG"]), cxxpp_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(dmd_flags=["-DFLAG"]), dmd_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(gcc_flags=["-DFLAG"]), gcc_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(gdc_flags=["-DFLAG"]), gdc_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(ghc_flags=["-DFLAG"]), ghc_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(java_flags=["-DFLAG"]), java_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(ldc_flags=["-DFLAG"]), ldc_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(ld_flags=["-DFLAG"]), ld_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(par_flags=["-DFLAG"]), par_flags=["-DFLAG_TWO"])',
            'extend_build_mode(create_build_mode(asan_options={"a":"1"}), asan_options={"z":"100"})',
            'extend_build_mode(create_build_mode(ubsan_options={"b":"2"}), ubsan_options={"y":"99"})',
            'extend_build_mode(create_build_mode(tsan_options={"c":"3"}), tsan_options={"x":"98"})',
            'extend_build_mode(create_build_mode(lsan_suppressions=["a/b/c"]), lsan_suppressions=["z/y/x"])',
            'extend_build_mode(create_build_mode(cxx_modules=False), cxx_modules=True)',
            'extend_build_mode(create_build_mode(asan_options={"a":"1"}), cxx_flags=["-DFLAG"])',
            'extend_build_mode(create_build_mode(compiler="foo"), cxx_flags=["-DFLAG"])',
            'extend_build_mode(create_build_mode(compiler="foo"), compiler="bar")',
        ]
        expected = [
            self._create_mode_struct(aspp_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(c_flags=("-DFLAG", "-DFLAG_TWO")),
            self._create_mode_struct(clang_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(cpp_flags=("-DFLAG", "-DFLAG_TWO")),
            self._create_mode_struct(cxx_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(cxxpp_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(dmd_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(gcc_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(gdc_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(ghc_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(java_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(ldc_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(ld_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(par_flags=["-DFLAG", "-DFLAG_TWO"]),
            self._create_mode_struct(asan_options={"a":"1", "z":"100"}),
            self._create_mode_struct(ubsan_options={"b":"2", "y":"99"}),
            self._create_mode_struct(tsan_options={"c":"3", "x":"98"}),
            self._create_mode_struct(lsan_suppressions=["a/b/c", "z/y/x"]),
            self._create_mode_struct(cxx_modules=True),
            self._create_mode_struct(cxx_flags=("-DFLAG",),asan_options={"a":"1"}),
            self._create_mode_struct(compiler="foo",cxx_flags=("-DFLAG",)),
            self._create_mode_struct(compiler="bar"),
        ]
        result = root.runUnitTests(self.includes, statements)
        self.assertSuccess(result, *expected)

    @tests.utils.with_project()
    def test_get_correct_build_mode_for_current_build_file(self, root):
        build_mode_override = dedent("""
            load(
                "@fbcode_macros//build_defs:create_build_mode.bzl",
                "create_build_mode",
            )
            def dev():
                return {
                    "dev": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def dbg():
                return {
                    "dbg": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def opt():
                return {
                    "opt": create_build_mode(c_flags=["-DDEBUG"]),
                }
            build_mode_overrides = {"fbcode": {
                "foo/bar": dev,
                "foo/bar-other": dbg,
                "foo": opt,
            }}

        """)
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl",
            build_mode_override)

        result1 = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_modes_for_current_buildfile()"],
            buckfile="foo/bar/baz/BUCK"
        )
        result2 = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_modes_for_current_buildfile()"],
            buckfile="foo/bar/BUCK"
        )
        result3 = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_modes_for_current_buildfile()"],
            buckfile="foo/bar-other/BUCK"
        )
        result4 = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_modes_for_current_buildfile()"],
            buckfile="foo/baz/BUCK",
        )
        result5 = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_modes_for_current_buildfile()"],
            buckfile="foo/BUCK",
        )
        result6 = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_modes_for_current_buildfile()"],
            buckfile="foobar/BUCK",
        )

        expected = self.struct(
            aspp_flags=(),
            cpp_flags=(),
            cxxpp_flags=(),
            c_flags=["-DDEBUG"],
            cxx_flags=(),
            ld_flags=(),
            clang_flags=(),
            gcc_flags=(),
            java_flags=(),
            dmd_flags=(),
            gdc_flags=(),
            ldc_flags=(),
            par_flags=(),
            ghc_flags=(),
            asan_options=(),
            ubsan_options=(),
            tsan_options=(),
            lsan_suppressions=(),
            cxx_modules=None,
            compiler=None)

        self.assertSuccess(result1, {"dev": expected})
        self.assertSuccess(result2, {"dev": expected})
        self.assertSuccess(result3, {"dbg": expected})
        self.assertSuccess(result4, {"opt": expected})
        self.assertSuccess(result5, {"opt": expected})
        self.assertSuccess(result6, {})

    @tests.utils.with_project()
    def test_get_correct_build_mode_for_base_path(self, root):
        build_mode_override = dedent("""
            load(
                "@fbcode_macros//build_defs:create_build_mode.bzl",
                "create_build_mode",
            )
            def dev():
                return {
                    "dev": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def dbg():
                return {
                    "dbg": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def opt():
                return {
                    "opt": create_build_mode(c_flags=["-DDEBUG"]),
                }
            build_mode_overrides = {"fbcode": {
                "foo/bar": dev,
                "foo/bar-other": dbg,
                "foo": opt,
            }}
        """)
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl",
            build_mode_override)

        result = root.runUnitTests(self.includes, [
            'build_mode.get_build_modes_for_base_path("foo/bar/baz")',
            'build_mode.get_build_modes_for_base_path("foo/bar")',
            'build_mode.get_build_modes_for_base_path("foo/bar-other")',
            'build_mode.get_build_modes_for_base_path("foo/baz")',
            'build_mode.get_build_modes_for_base_path("foo")',
            'build_mode.get_build_modes_for_base_path("foobar")',
        ])

        expected = self.struct(
            aspp_flags=(),
            cpp_flags=(),
            cxxpp_flags=(),
            c_flags=["-DDEBUG"],
            cxx_flags=(),
            ld_flags=(),
            clang_flags=(),
            gcc_flags=(),
            java_flags=(),
            dmd_flags=(),
            gdc_flags=(),
            ldc_flags=(),
            par_flags=(),
            ghc_flags=(),
            asan_options=(),
            ubsan_options=(),
            tsan_options=(),
            lsan_suppressions=(),
            cxx_modules=None,
            compiler=None)

        self.assertSuccess(
            result,
            {"dev": expected},
            {"dev": expected},
            {"dbg": expected},
            {"opt": expected},
            {"opt": expected},
            {},
        )

    @tests.utils.with_project()
    def test_get_build_mode_overrides(self, root):
        build_mode_override = dedent("""
            load(
                "@fbcode_macros//build_defs:create_build_mode.bzl",
                "create_build_mode",
            )
            def dev():
                return {
                    "dev": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def dbg():
                return {
                    "dbg": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def opt():
                return {
                    "opt": create_build_mode(c_flags=["-DDEBUG"]),
                }
            build_mode_overrides = {"fbcode": {
                "foo/bar": dev,
                "foo/bar-other": dbg,
                "foo": opt,
            }}
        """)
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl",
            build_mode_override)

        expected = {
            "fbcode": {
                "foo/bar": {
                    "dev": self._create_mode_struct(c_flags=["-DDEBUG"]),
                },
                "foo/bar-other": {
                    "dbg": self._create_mode_struct(c_flags=["-DDEBUG"]),
                },
                "foo": {
                    "opt": self._create_mode_struct(c_flags=["-DDEBUG"]),
                },
            }
        }

        result = root.runUnitTests(
            self.includes,
            ["build_mode.get_build_mode_overrides()"],
        )

        self.assertSuccess(result, expected)

    @tests.utils.with_project()
    def test_helper_util_runs_properly(self, root):
        build_mode_override = dedent("""
            load(
                "@fbcode_macros//build_defs:create_build_mode.bzl",
                "create_build_mode",
            )
            def dev():
                return {
                    "dev": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def dbg():
                return {
                    "dbg": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def opt():
                return {
                    "opt": create_build_mode(c_flags=["-DDEBUG"]),
                }
            build_mode_overrides = {"fbcode": {
                "foo/bar": dev,
                "foo/bar-other": dbg,
                "foo": opt,
            }}
        """)
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl",
            build_mode_override)

        result = root.run([
            "buck",
            "run",
            "fbcode_macros//tools:get_build_mode",
            "foo/bar/baz",
            "foo/bar",
            "foo/bar-other",
            "foo/baz",
            "foo",
            "foobar",
        ], {}, {})

        expected_mode = {
            "aspp_flags": [],
            "cpp_flags": [],
            "cxxpp_flags": [],
            "c_flags": ["-DDEBUG"],
            "cxx_flags": [],
            "ld_flags": [],
            "clang_flags": [],
            "gcc_flags": [],
            "java_flags": [],
            "dmd_flags": [],
            "gdc_flags": [],
            "ldc_flags": [],
            "par_flags": [],
            "ghc_flags": [],
            "asan_options": [],
            "tsan_options": [],
            "ubsan_options": [],
            "lsan_suppressions": [],
            "cxx_modules": None,
            "compiler": None,
        }
        expected = [
            ("foo/bar/baz", {"dev": expected_mode}),
            ("foo/bar", {"dev": expected_mode}),
            ("foo/bar-other", {"dbg": expected_mode}),
            ("foo/baz", {"opt": expected_mode}),
            ("foo", {"opt": expected_mode}),
            ("foobar", {}),
        ]

        self.assertSuccess(result)
        print(result.stdout)
        actual = [
            (line.split(":", 1)[0], json.loads(line.split(":", 1)[1]))
            for line in result.stdout.split("\n")
            if line
        ]
        self.assertEqual(expected, actual)
