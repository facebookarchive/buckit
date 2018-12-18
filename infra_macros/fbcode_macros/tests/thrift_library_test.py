# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import json

import tests.utils
from tests.utils import dedent


class ThriftLibraryTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:thrift_library.bzl", "thrift_library")]

    @tests.utils.with_project()
    def test_thrift_library_parses(self, root):
        root.addFile(
            "BUCK",
            dedent(
                """
            load("@fbcode_macros//build_defs:thrift_library.bzl", "thrift_library")
            thrift_library(
                name = "some_lib",
                thrift_srcs = {"foo.thrift": []},
                languages =  [
                    "py",
                    "hs",
                    "py-twisted",
                    "cpp2",
                    "py-asyncio",
                    "pyi",
                    "rust",
                    "js",
                    "java-swift",
                    "javadeprecated-apache",
                    "go",
                    "javadeprecated",
                    "hs2",
                    "thriftdoc-py",
                    "ocaml2",
                    "py3",
                    "d",
                    "pyi-asyncio",
                ],
                plugins = (),
                visibility = None,
                thrift_args = ["--foo-bar"],
                deps = ["//some:thrift_lib"],

                cpp2_compiler_flags = ["cpp2_compiler_flags"],
                cpp2_deps = ["//cpp2:some_lib"],
                cpp2_external_deps = [("glog", None, "glog")],
                cpp2_headers = ["header.h"],
                cpp2_srcs = ["src.cpp"],
                thrift_cpp2_options = ["json"],
            )

            """
            ),
        )

        self.assertSuccess(root.runAudit(["BUCK"]))

    @tests.utils.with_project()
    def test_cpp2_auto_included_in_py3_rules(self, root):
        root.updateBuckconfig("thrift", "compiler", "//:compiler")
        root.updateBuckconfig("thrift", "compiler2", "//:compiler")
        root.updateBuckconfig("cython", "cython_compiler", "//:compiler")
        root.updateBuckconfig("thrift", "templates", "//:templates")
        contents = dedent(
            """
        load("@fbcode_macros//build_defs:thrift_library.bzl", "thrift_library")
        sh_binary(name="compiler", main="compiler.sh")
        filegroup(name="templates", srcs=glob(["*"]))

        thrift_library(
            name = "name",
            thrift_srcs={"service.thrift": []},
            languages=[
                "py3",
            ],
        )
        """
        )
        root.addFile("BUCK", contents)
        root.addFile("compiler.sh", "", executable=True)
        root.addFile("service.thrift", "")

        result = root.run(
            ["buck", "query", "--json", "--output-attribute=buck.type", "//:"], {}, {}
        )
        self.assertSuccess(result)
        self.assertEqual(
            "cxx_library", json.loads(result.stdout)["//:name-cpp2"]["buck.type"]
        )

    @tests.utils.with_project()
    def test_cpp2_options_copy_to_py3_options_in_py3_rules(self, root):
        root.updateBuckconfig("thrift", "compiler", "//:compiler")
        root.updateBuckconfig("thrift", "compiler2", "//:compiler")
        root.updateBuckconfig("cython", "cython_compiler", "//:compiler")
        root.updateBuckconfig("thrift", "templates", "//:templates")
        contents = dedent(
            """
        load("@fbcode_macros//build_defs:thrift_library.bzl", "thrift_library")
        sh_binary(name="compiler", main="compiler.sh")
        filegroup(name="templates", srcs=glob(["*"]))

        thrift_library(
            name = "name",
            thrift_srcs={"service.thrift": []},
            languages=[
                "py3", "cpp2",
            ],
            thrift_cpp2_options="BLAH",
        )
        """
        )
        root.addFile("BUCK", contents)
        root.addFile("compiler.sh", "", executable=True)
        root.addFile("service.thrift", "")

        result = root.run(
            ["buck", "query", "--json", "--output-attribute=cmd", "//:"], {}, {}
        )
        self.assertSuccess(result)
        self.assertIn(
            "BLAH", json.loads(result.stdout)["//:name-py3-service.thrift"]["cmd"]
        )
