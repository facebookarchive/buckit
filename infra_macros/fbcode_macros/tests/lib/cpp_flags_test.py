# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class CppFlagsTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs/lib:cpp_flags.bzl", "cpp_flags")]

    @tests.utils.with_project()
    def test_get_extra_flags_methods(self, root):
        root.updateBuckconfig("cxx", "extra_cflags", "-DCFLAG1 -DCFLAG2='true value'")
        root.updateBuckconfig(
            "cxx", "extra_cxxflags", "-DCXXFLAG1 -DCXXFLAG2='true value'"
        )
        root.updateBuckconfig(
            "cxx", "extra_cppflags", "-DCPPFLAG1 -DCPPFLAG2='true value'"
        )
        root.updateBuckconfig(
            "cxx", "extra_cxxppflags", "-DCXXPPFLAG1 -DCXXPPFLAG2='true value'"
        )
        root.updateBuckconfig(
            "cxx", "extra_ldflags", "-DLDFLAG1 -DLDFLAG2='true value'"
        )

        commands = [
            "cpp_flags.get_extra_cflags()",
            "cpp_flags.get_extra_cxxflags()",
            "cpp_flags.get_extra_cppflags()",
            "cpp_flags.get_extra_cxxppflags()",
            "cpp_flags.get_extra_ldflags()",
        ]
        expected = [
            ["-DCFLAG1", "-DCFLAG2=true value"],
            ["-DCXXFLAG1", "-DCXXFLAG2=true value"],
            ["-DCPPFLAG1", "-DCPPFLAG2=true value"],
            ["-DCXXPPFLAG1", "-DCXXPPFLAG2=true value"],
            ["-DLDFLAG1", "-DLDFLAG2=true value"],
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_get_compiler_flags_with_no_sanitizer_or_build_mode_file(self, root):
        root.updateBuckconfig("cxx", "extra_cflags", "-Dcflag1 -Dcflag2")
        root.updateBuckconfig("cxx", "extra_cxxflags", "-Dcxxflag1 -Dcxxflag2")

        cflags = ["-Dcflag1", "-Dcflag2"]
        cxxflags = ["-Dcxxflag1", "-Dcxxflag2"]

        commands = ['cpp_flags.get_compiler_flags("foo")']
        expected = {
            "asm": [],
            "assembler": [],
            "c_cpp_output": [
                ("^default-clang$", cflags),
                ("^default-gcc$", cflags),
                ("^gcc5-clang$", cflags),
                ("^gcc5-gcc$", cflags),
                ("^gcc6-clang$", cflags),
                ("^gcc6-gcc$", cflags),
                ("^gcc7-clang$", cflags),
                ("^gcc7-gcc$", cflags),
            ],
            "cuda_cpp_output": [],
            "cxx_cpp_output": [
                ("^default-clang$", cxxflags),
                ("^default-gcc$", cxxflags),
                ("^gcc5-clang$", cxxflags),
                ("^gcc5-gcc$", cxxflags),
                ("^gcc6-clang$", cxxflags),
                ("^gcc6-gcc$", cxxflags),
                ("^gcc7-clang$", cxxflags),
                ("^gcc7-gcc$", cxxflags),
            ],
        }

        result = root.runUnitTests(self.includes, commands)
        self.assertSuccess(result)
        self.assertEqual(
            expected, {k: sorted(v) for k, v in result.debug_lines[0].items()}
        )

    @tests.utils.with_project()
    def test_get_compiler_flags_with_sanitizer_and_no_build_mode_file(self, root):
        root.updateBuckconfig("cxx", "extra_cflags", "-Dcflag1 -Dcflag2")
        root.updateBuckconfig("cxx", "extra_cxxflags", "-Dcxxflag1 -Dcxxflag2")
        root.updateBuckconfig("fbcode", "sanitizer", "thread")
        root.updateBuckconfig("fbcode", "global_compiler", "clang")

        sanitizer_flags = [
            "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer",
            "-fdata-sections",
            "-ffunction-sections",
            "-fsanitize=thread",
        ]
        cflags = ["-Dcflag1", "-Dcflag2"]
        cxxflags = ["-Dcxxflag1", "-Dcxxflag2"]

        commands = ['cpp_flags.get_compiler_flags("foo")']
        expected = {
            "asm": [],
            "assembler": [
                ("^default-clang$", sanitizer_flags),
                ("^gcc5-clang$", sanitizer_flags),
                ("^gcc6-clang$", sanitizer_flags),
                ("^gcc7-clang$", sanitizer_flags),
            ],
            "c_cpp_output": [
                ("^default-clang$", sanitizer_flags),
                ("^gcc5-clang$", sanitizer_flags),
                ("^gcc6-clang$", sanitizer_flags),
                ("^gcc7-clang$", sanitizer_flags),
                ("^default-clang$", cflags),
                ("^gcc5-clang$", cflags),
                ("^gcc6-clang$", cflags),
                ("^gcc7-clang$", cflags),
            ],
            "cuda_cpp_output": [],
            "cxx_cpp_output": [
                ("^default-clang$", sanitizer_flags),
                ("^gcc5-clang$", sanitizer_flags),
                ("^gcc6-clang$", sanitizer_flags),
                ("^gcc7-clang$", sanitizer_flags),
                ("^default-clang$", cxxflags),
                ("^gcc5-clang$", cxxflags),
                ("^gcc6-clang$", cxxflags),
                ("^gcc7-clang$", cxxflags),
            ],
        }

        result = root.runUnitTests(self.includes, commands)
        self.assertSuccess(result)
        self.assertEqual(
            {k: sorted(v) for k, v in expected.items()},
            {k: sorted(v) for k, v in result.debug_lines[0].items()},
        )

    @tests.utils.with_project()
    def test_get_compiler_flags_with_sanitizer_clang_and_build_mode_file(self, root):
        root.updateBuckconfig("cxx", "extra_cflags", "-Dcflag1 -Dcflag2")
        root.updateBuckconfig("cxx", "extra_cxxflags", "-Dcxxflag1 -Dcxxflag2")
        root.updateBuckconfig("fbcode", "sanitizer", "thread")
        root.updateBuckconfig("fbcode", "global_compiler", "clang")
        root.updateBuckconfig("fbcode", "build_mode", "dev")

        sanitizer_flags = [
            "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer",
            "-fdata-sections",
            "-ffunction-sections",
            "-fsanitize=thread",
        ]
        bm_clangflags = ["-DCLANG"]
        bm_gccflags = ["-DGCC"]
        bm_cflags = ["-DDEBUG"]
        bm_cxxflags = ["-DCXX_DEBUG"]
        cflags = ["-Dcflag1", "-Dcflag2"]
        cxxflags = ["-Dcxxflag1", "-Dcxxflag2"]

        commands = ['cpp_flags.get_compiler_flags("foo/bar")']
        expected = {
            "asm": [],
            "assembler": [
                ("^default-clang$", sanitizer_flags),
                ("^gcc5-clang$", sanitizer_flags),
                ("^gcc6-clang$", sanitizer_flags),
                ("^gcc7-clang$", sanitizer_flags),
                ("^default-clang$", bm_clangflags),
                ("^gcc5-clang$", bm_clangflags),
                ("^gcc6-clang$", bm_clangflags),
                ("^gcc7-clang$", bm_clangflags),
            ],
            "c_cpp_output": [
                ("^default-clang$", sanitizer_flags),
                ("^gcc5-clang$", sanitizer_flags),
                ("^gcc6-clang$", sanitizer_flags),
                ("^gcc7-clang$", sanitizer_flags),
                ("^default-clang$", bm_clangflags),
                ("^gcc5-clang$", bm_clangflags),
                ("^gcc6-clang$", bm_clangflags),
                ("^gcc7-clang$", bm_clangflags),
                ("^default-clang$", bm_cflags),
                ("^gcc5-clang$", bm_cflags),
                ("^gcc6-clang$", bm_cflags),
                ("^gcc7-clang$", bm_cflags),
                ("^default-clang$", cflags),
                ("^gcc5-clang$", cflags),
                ("^gcc6-clang$", cflags),
                ("^gcc7-clang$", cflags),
            ],
            "cuda_cpp_output": [
                ("^default-clang$", bm_gccflags),
                ("^gcc5-clang$", bm_gccflags),
                ("^gcc6-clang$", bm_gccflags),
                ("^gcc7-clang$", bm_gccflags),
            ],
            "cxx_cpp_output": [
                ("^default-clang$", sanitizer_flags),
                ("^gcc5-clang$", sanitizer_flags),
                ("^gcc6-clang$", sanitizer_flags),
                ("^gcc7-clang$", sanitizer_flags),
                ("^default-clang$", bm_clangflags),
                ("^gcc5-clang$", bm_clangflags),
                ("^gcc6-clang$", bm_clangflags),
                ("^gcc7-clang$", bm_clangflags),
                ("^default-clang$", bm_cxxflags),
                ("^gcc5-clang$", bm_cxxflags),
                ("^gcc6-clang$", bm_cxxflags),
                ("^gcc7-clang$", bm_cxxflags),
                ("^default-clang$", cxxflags),
                ("^gcc5-clang$", cxxflags),
                ("^gcc6-clang$", cxxflags),
                ("^gcc7-clang$", cxxflags),
            ],
        }

        result = root.runUnitTests(self.includes, commands, buckfile="foo/bar/BUCK")
        self.assertSuccess(result)
        self.assertEqual(
            {k: sorted(v) for k, v in expected.items()},
            {k: sorted(v) for k, v in result.debug_lines[0].items()},
        )

    @tests.utils.with_project()
    def test_get_compiler_flags_without_sanitizer_gcc_and_build_mode_file(self, root):
        root.updateBuckconfig("cxx", "extra_cflags", "-Dcflag1 -Dcflag2")
        root.updateBuckconfig("cxx", "extra_cxxflags", "-Dcxxflag1 -Dcxxflag2")
        root.updateBuckconfig("fbcode", "global_compiler", "gcc")
        root.updateBuckconfig("fbcode", "build_mode", "dev")

        bm_gccflags = ["-DGCC"]
        bm_cflags = ["-DDEBUG"]
        bm_cxxflags = ["-DCXX_DEBUG"]
        cflags = ["-Dcflag1", "-Dcflag2"]
        cxxflags = ["-Dcxxflag1", "-Dcxxflag2"]

        commands = ['cpp_flags.get_compiler_flags("foo/bar")']
        expected = {
            "asm": [],
            "assembler": [
                ("^default-gcc$", bm_gccflags),
                ("^gcc5-gcc$", bm_gccflags),
                ("^gcc6-gcc$", bm_gccflags),
                ("^gcc7-gcc$", bm_gccflags),
            ],
            "c_cpp_output": [
                ("^default-gcc$", bm_gccflags),
                ("^gcc5-gcc$", bm_gccflags),
                ("^gcc6-gcc$", bm_gccflags),
                ("^gcc7-gcc$", bm_gccflags),
                ("^default-gcc$", bm_cflags),
                ("^gcc5-gcc$", bm_cflags),
                ("^gcc6-gcc$", bm_cflags),
                ("^gcc7-gcc$", bm_cflags),
                ("^default-gcc$", cflags),
                ("^gcc5-gcc$", cflags),
                ("^gcc6-gcc$", cflags),
                ("^gcc7-gcc$", cflags),
            ],
            "cuda_cpp_output": [
                ("^default-gcc$", bm_gccflags),
                ("^gcc5-gcc$", bm_gccflags),
                ("^gcc6-gcc$", bm_gccflags),
                ("^gcc7-gcc$", bm_gccflags),
            ],
            "cxx_cpp_output": [
                ("^default-gcc$", bm_gccflags),
                ("^gcc5-gcc$", bm_gccflags),
                ("^gcc6-gcc$", bm_gccflags),
                ("^gcc7-gcc$", bm_gccflags),
                ("^default-gcc$", bm_cxxflags),
                ("^gcc5-gcc$", bm_cxxflags),
                ("^gcc6-gcc$", bm_cxxflags),
                ("^gcc7-gcc$", bm_cxxflags),
                ("^default-gcc$", cxxflags),
                ("^gcc5-gcc$", cxxflags),
                ("^gcc6-gcc$", cxxflags),
                ("^gcc7-gcc$", cxxflags),
            ],
        }

        result = root.runUnitTests(self.includes, commands, buckfile="foo/bar/BUCK")
        self.assertSuccess(result)
        self.assertEqual(
            {k: sorted(v) for k, v in expected.items()},
            {k: sorted(v) for k, v in result.debug_lines[0].items()},
        )
