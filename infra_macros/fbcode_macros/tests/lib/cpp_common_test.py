# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CppCommonTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")]

    @tests.utils.with_project()
    def test_default_headers_library_works(self, root):
        buckfile = "subdir/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
        cpp_common.default_headers_library()
        cpp_common.default_headers_library()
        """
            ),
        )

        files = [
            "subdir/foo.cpp",
            "subdir/foo.h",
            "subdir/foo.hh",
            "subdir/foo.tcc",
            "subdir/foo.hpp",
            "subdir/foo.cuh",
            "subdir/foo/bar.cpp",
            "subdir/foo/bar.h",
            "subdir/foo/bar.hh",
            "subdir/foo/bar.tcc",
            "subdir/foo/bar.hpp",
            "subdir/foo/bar.cuh",
        ]
        for file in files:
            root.addFile(file, "")

        expected = {
            buckfile: dedent(
                r"""
                cxx_library(
                  name = "__default_headers__",
                  default_platform = "default-gcc",
                  defaults = {
                    "platform": "default-gcc",
                  },
                  exported_headers = [
                    "foo.cuh",
                    "foo.h",
                    "foo.hh",
                    "foo.hpp",
                    "foo.tcc",
                    "foo/bar.cuh",
                    "foo/bar.h",
                    "foo/bar.hh",
                    "foo/bar.hpp",
                    "foo/bar.tcc",
                  ],
                  labels = [
                    "is_fully_translated",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))

    @tests.utils.with_project()
    def test_is_cpp_source(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                [
                    'cpp_common.is_cpp_source("foo.cpp")',
                    'cpp_common.is_cpp_source("foo.cc")',
                    'cpp_common.is_cpp_source("foo.c")',
                    'cpp_common.is_cpp_source("foo.h")',
                ],
            ),
            True,
            True,
            False,
            False,
        )

    @tests.utils.with_project()
    def test_exclude_from_auto_pch(self, root):
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/auto_pch_blacklist.bzl",
            dedent(
                """
                load("@bazel_skylib//lib:new_sets.bzl", "sets")
                auto_pch_blacklist = sets.make(["exclude", "exclude2/subdir"])
                """
            ),
        )
        commands = [
            'cpp_common.exclude_from_auto_pch("//test", "path")',
            'cpp_common.exclude_from_auto_pch("test//test", "path")',
            'cpp_common.exclude_from_auto_pch("//exclude2", "path")',
            'cpp_common.exclude_from_auto_pch("exclude2//exclude2", "path")',
            'cpp_common.exclude_from_auto_pch("//exclude", "path")',
            'cpp_common.exclude_from_auto_pch("exclude//exclude", "path")',
            'cpp_common.exclude_from_auto_pch("//exclude/dir1", "path")',
            'cpp_common.exclude_from_auto_pch("exclude//exclude/dir1", "path")',
            'cpp_common.exclude_from_auto_pch("//exclude/dir1/dir2", "path")',
            'cpp_common.exclude_from_auto_pch("exclude//exclude/dir1/dir2", "path")',
            'cpp_common.exclude_from_auto_pch("//exclude2/subdir", "path")',
            'cpp_common.exclude_from_auto_pch("exclude2//exclude2/subdir", "path")',
            'cpp_common.exclude_from_auto_pch("//exclude2/subdir/dir2", "path")',
            'cpp_common.exclude_from_auto_pch("exclude2//exclude2/subdir/dir2", "path")',
        ]

        expected = [
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project(run_buckd=True)
    def test_get_link_style(self, root):
        commands = ["cpp_common.get_link_style()"]

        expected = ["static", "shared", "static_pic"]
        expected_tsan = ["static_pic", "shared", "static_pic"]

        root.updateBuckconfig("defaults.cxx_library", "type", "static")
        self.assertSuccess(root.runUnitTests(self.includes, commands), expected[0])
        root.updateBuckconfig("defaults.cxx_library", "type", "shared")
        self.assertSuccess(root.runUnitTests(self.includes, commands), expected[1])
        root.updateBuckconfig("defaults.cxx_library", "type", "static_pic")
        self.assertSuccess(root.runUnitTests(self.includes, commands), expected[2])

        root.updateBuckconfig("fbcode", "sanitizer", "thread")
        root.updateBuckconfig("defaults.cxx_library", "type", "static")
        self.assertSuccess(root.runUnitTests(self.includes, commands), expected_tsan[0])
        root.updateBuckconfig("defaults.cxx_library", "type", "shared")
        self.assertSuccess(root.runUnitTests(self.includes, commands), expected_tsan[1])
        root.updateBuckconfig("defaults.cxx_library", "type", "static_pic")
        self.assertSuccess(root.runUnitTests(self.includes, commands), expected_tsan[2])

    @tests.utils.with_project(run_buckd=True)
    def test_get_binary_link_deps(self, root):
        commands = [
            'cpp_common.get_binary_link_deps("foo", "bar", ["-fuse-ld=gold"], allocator="jemalloc", default_deps=True)',
            'cpp_common.get_binary_link_deps("foo", "baz", ["-fuse-ld=gold"], allocator="jemalloc", default_deps=False)',
        ]

        expected = [
            [
                self.rule_target(base_path="common/memory", name="jemalloc", repo=None),
                self.rule_target(
                    base_path="foo", name="bar-san-conf-__generated-lib__", repo=None
                ),
                self.rule_target(base_path="common/init", name="kill", repo=None),
            ],
            [
                self.rule_target(base_path="common/memory", name="jemalloc", repo=None),
                self.rule_target(
                    base_path="foo", name="baz-san-conf-__generated-lib__", repo=None
                ),
            ],
        ]

        expected_san = [
            [
                self.rule_target(
                    base_path="tools/build/sanitizers", name="asan-cpp", repo=None
                ),
                self.rule_target(
                    base_path="foo", name="bar-san-conf-__generated-lib__", repo=None
                ),
                self.rule_target(base_path="common/init", name="kill", repo=None),
            ],
            [
                self.rule_target(
                    base_path="tools/build/sanitizers", name="asan-cpp", repo=None
                ),
                self.rule_target(
                    base_path="foo", name="baz-san-conf-__generated-lib__", repo=None
                ),
            ],
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

        root.updateBuckconfig("fbcode", "global_compiler", "clang")
        root.updateBuckconfig("fbcode", "sanitizer", "address")
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected_san)

    @tests.utils.with_project(run_buckd=True)
    def test_cxx_build_info_rule(self, root):
        root.updateBuckconfigWithDict(
            {
                "build_info": {
                    "epochtime": "1234",
                    "host": "fb.example.com",
                    "package_name": "some_package_app",
                    "package_version": "1.0",
                    "package_release": "5",
                    "path": "/home/pjameson/some-repo",
                    "revision": "5821da1851c676d3ad584a6a2670fa3e9d30baa4",
                    "revision_epochtime": "2345",
                    "time": "12:01:59",
                    "time_iso8601": "2018-07-17T12:01:59Z",
                    "upstream_revision": "0e427bf1c3b8e44ccb59554ae2ee610be6b5a054",
                    "upstream_revision_epochtime": "3456",
                    "user": "pjameson",
                }
            }
        )
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
            cpp_common.cxx_build_info_rule(
                base_path="",
                name="foo",
                rule_type="cpp_binary",
                platform="gcc5",
                static = True,
                visibility = None,
            )
            """
            ),
        )

        expected = {
            "BUCK": dedent(
                r"""
genrule(
  name = "foo-cxx-build-info",
  cmd = "mkdir -p `dirname $OUT` && echo \'#include <stdint.h>

const char* const BuildInfo_kBuildMode = \"dev\";
const char* const BuildInfo_kBuildTool = \"buck\";
const char* const BuildInfo_kCompiler = \"gcc\";
const char* const BuildInfo_kHost = \"fb.example.com\";
const char* const BuildInfo_kPackageName = \"some_package_app\";
const char* const BuildInfo_kPackageVersion = \"1.0\";
const char* const BuildInfo_kPackageRelease = \"5\";
const char* const BuildInfo_kPath = \"/home/pjameson/some-repo\";
const char* const BuildInfo_kPlatform = \"gcc5\";
const char* const BuildInfo_kRevision = \"5821da1851c676d3ad584a6a2670fa3e9d30baa4\";
const char* const BuildInfo_kRule = \"fbcode::foo\";
const char* const BuildInfo_kRuleType = \"cpp_binary\";
const char* const BuildInfo_kTime = \"12:01:59\";
const char* const BuildInfo_kTimeISO8601 = \"2018-07-17T12:01:59Z\";
const char* const BuildInfo_kUpstreamRevision = \"0e427bf1c3b8e44ccb59554ae2ee610be6b5a054\";
const char* const BuildInfo_kUser = \"pjameson\";
const uint64_t BuildInfo_kRevisionCommitTimeUnix = 2345;
const uint64_t BuildInfo_kTimeUnix = 1234;
const uint64_t BuildInfo_kUpstreamRevisionCommitTimeUnix =
  3456;
\' > $OUT",
  labels = [
    "generated",
    "is_fully_translated",
  ],
  out = "foo-cxx-build-info.c",
)

cxx_library(
  name = "foo-cxx-build-info-lib",
  default_platform = "default-gcc",
  defaults = {
    "platform": "default-gcc",
  },
  force_static = True,
  labels = [
    "generated",
    "is_fully_translated",
  ],
  link_whole = True,
  linker_flags = [
    "-nodefaultlibs",
  ],
  srcs = [
    ":foo-cxx-build-info",
  ],
)
                """
            )
        }

        self.validateAudit(expected, root.runAudit(["BUCK"]))
