# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class NativeRulesTest(tests.utils.TestCase):

    import_lines = dedent(
        """
        load("@fbcode_macros//build_defs:native_rules.bzl",
            "buck_command_alias",
            "buck_filegroup",
            "cxx_genrule",
            "buck_genrule",
            "buck_python_binary",
            "buck_python_library",
            "remote_file",
            "buck_sh_binary",
            "buck_sh_test",
            "versioned_alias",
            "buck_cxx_binary",
            "buck_cxx_library",
            "buck_cxx_test",
            "test_suite",
        )
        """
    )

    @tests.utils.with_project()
    def test_ungated_rules_propagate_properly(self, root):
        root.addFile(
            "BUCK",
            self.import_lines
            + "\n"
            + dedent(
                """
            buck_command_alias(name="command_alias", exe=":sh_binary")
            buck_filegroup(name="filegroup", srcs=["python_library.py"])
            cxx_genrule(name="cxx_genrule", out="out.h", cmd="echo > $OUT")
            buck_genrule(name="genrule", out="out", cmd="echo > $OUT")
            buck_python_binary(name="python_binary", deps=[":python_library"], main_module="python_binary")
            buck_python_library(name="python_library", srcs=["python_library.py"])
            remote_file(
                name="file",
                url="http://example.com/foo",
                sha1="d8b7ec2e8d5a713858d12bb8a8e22a4dad2abb04",
            )
            buck_sh_binary(name="sh_binary", main="sh_binary.sh")
            buck_sh_binary(name="sh_binary2.sh")
            buck_sh_test(name="sh_test", test="sh_test.sh")
            test_suite(name="all_tests", tests=[":sh_test"])
            versioned_alias(
                name="versioned_alias",
                versions={
                    "1.0": ":sh_binary",
                    "1.1": ":sh_binary",
                },
            )
        """
            ),
        )

        expected = dedent(
            """
            test_suite(
              name = "all_tests",
              labels = [
                "is_fully_translated",
              ],
              tests = [
                ":sh_test",
              ],
              visibility = [
                "PUBLIC",
              ],
            )

            command_alias(
              name = "command_alias",
              exe = ":sh_binary",
              labels = [
                "is_fully_translated",
              ],
            )

            cxx_genrule(
              name = "cxx_genrule",
              cmd = "echo > $OUT",
              labels = [
                "is_fully_translated",
              ],
              out = "out.h",
            )

            remote_file(
              name = "file",
              labels = [
                "is_fully_translated",
              ],
              sha1 = "d8b7ec2e8d5a713858d12bb8a8e22a4dad2abb04",
              url = "http://example.com/foo",
            )

            filegroup(
              name = "filegroup",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "python_library.py",
              ],
            )

            genrule(
              name = "genrule",
              cmd = "echo > $OUT",
              labels = [
                "is_fully_translated",
              ],
              out = "out",
            )

            python_binary(
              name = "python_binary",
              labels = [
                "is_fully_translated",
              ],
              main_module = "python_binary",
              deps = [
                ":python_library",
              ],
            )

            python_library(
              name = "python_library",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "python_library.py",
              ],
            )

            sh_binary(
              name = "sh_binary",
              labels = [
                "is_fully_translated",
              ],
              main = "sh_binary.sh",
            )

            sh_binary(
              name = "sh_binary2.sh",
              labels = [
                "is_fully_translated",
              ],
              main = "sh_binary2.sh",
            )

            sh_test(
              name = "sh_test",
              labels = [
                "is_fully_translated",
              ],
              test = "sh_test.sh",
            )

            versioned_alias(
              name = "versioned_alias",
              versions = {
                "1.0": ":sh_binary",
                "1.1": ":sh_binary",
              },
            )

        """
        )
        results = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, results)

    @tests.utils.with_project()
    def test_python_library_generates_typing_file(self, root):
        root.addFile(
            "BUCK",
            self.import_lines
            + "\n"
            + dedent(
                """
            buck_python_binary(
                name="python_binary",
                deps=[":python_library"],
                main_module="python_binary",
            )

            buck_python_library(
                name="python_library",
                srcs=[
                    "python_library.py",
                ],
            )
        """
            ),
        )

        expected = dedent(
            r"""
            python_binary(
              name = "python_binary",
              labels = [
                "is_fully_translated",
              ],
              main_module = "python_binary",
              deps = [
                ":python_library",
              ],
            )

            python_library(
              name = "python_library",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "python_library.py",
              ],
            )

            genrule(
              name = "python_library-typing",
              cmd = "mkdir -p \"$OUT\"",
              labels = [
                "is_fully_translated",
              ],
              out = "root",
              visibility = [
                "PUBLIC",
              ],
            )
        """
        )
        root.updateBuckconfig("python", "typing_config", "//python:typing")

        results = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, results)

    @tests.utils.with_project()
    def test_gated_rules_reject_on_non_whitelisted(self, root):
        whitelist = (
            "cxx_library=foo:bar_lib,"
            "cxx_library=foo:bar_bin,"
            "cxx_test=foo:bar_test"
        )
        root.updateBuckconfig("fbcode", "forbid_raw_buck_rules", "true")
        root.updateBuckconfig("fbcode", "whitelisted_raw_buck_rules", whitelist)
        prefix = dedent(
            """
            load(
                "@fbcode_macros//build_defs:native_rules.bzl",
                "buck_cxx_binary", "buck_cxx_library", "buck_cxx_test"
            )
        """
        )
        target1 = prefix + '\nbuck_cxx_binary(name="bin", srcs=["main.cpp"])'
        target2 = prefix + '\nbuck_cxx_library(name="lib", srcs=["lib.cpp"])'
        target3 = prefix + '\nbuck_cxx_test(name="test", srcs=["test.cpp"])'

        root.addFile("target1/BUCK", target1)
        root.addFile("target2/BUCK", target2)
        root.addFile("target3/BUCK", target3)

        result1 = root.runAudit(["target1/BUCK"])
        result2 = root.runAudit(["target2/BUCK"])
        result3 = root.runAudit(["target3/BUCK"])

        self.assertFailureWithMessage(
            result1,
            "Unsupported access to Buck rules!",
            "cxx_binary(): native rule target1:bin is not whitelisted",
        )
        self.assertFailureWithMessage(
            result2,
            "Unsupported access to Buck rules!",
            "cxx_library(): native rule target2:bin is not whitelisted",
        )
        self.assertFailureWithMessage(
            result3,
            "Unsupported access to Buck rules!",
            "cxx_test(): native rule target3:bin is not whitelisted",
        )

    @tests.utils.with_project()
    def test_gated_rules_accept_on_whitelisted(self, root):
        whitelist = (
            "cxx_binary=foo:bar_bin," "cxx_library=foo:bar_lib," "cxx_test=foo:bar_test"
        )
        root.updateBuckconfig("fbcode", "forbid_raw_buck_rules", "true")
        root.updateBuckconfig("fbcode", "whitelisted_raw_buck_rules", whitelist)
        contents = dedent(
            """
            load(
                "@fbcode_macros//build_defs:native_rules.bzl",
                "buck_cxx_binary", "buck_cxx_library", "buck_cxx_test"
            )
            buck_cxx_binary(name="bar_bin", srcs=["main.cpp"])
            buck_cxx_library(name="bar_lib", srcs=["lib.cpp"])
            buck_cxx_test(name="bar_test", srcs=["test.cpp"])
        """
        )
        root.addFile("foo/BUCK", contents)

        expected = dedent(
            """
            cxx_binary(
              name = "bar_bin",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "main.cpp",
              ],
            )

            cxx_library(
              name = "bar_lib",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "lib.cpp",
              ],
            )

            cxx_test(
              name = "bar_test",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "test.cpp",
              ],
            )
        """
        )
        result = root.runAudit(["foo/BUCK"])

        self.validateAudit({"foo/BUCK": expected}, result)

    @tests.utils.with_project()
    def test_gated_rules_accepted_on_non_whitelisted_if_forbid_disabled(self, root):
        whitelist = (
            "cxx_binary=foo:bar_bin," "cxx_library=foo:bar_lib," "cxx_test=foo:bar_test"
        )
        root.updateBuckconfig("fbcode", "whitelisted_raw_buck_rules", whitelist)
        # don't forbid raw_rules by default
        contents = dedent(
            """
            load(
                "@fbcode_macros//build_defs:native_rules.bzl",
                "buck_cxx_binary", "buck_cxx_library", "buck_cxx_test"
            )
            buck_cxx_binary(name="bar_bin", srcs=["main.cpp"])
            buck_cxx_library(name="bar_lib", srcs=["lib.cpp"])
            buck_cxx_test(name="bar_test", srcs=["test.cpp"])
        """
        )
        root.addFile("not_foo/BUCK", contents)

        expected = dedent(
            """
            cxx_binary(
              name = "bar_bin",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "main.cpp",
              ],
            )

            cxx_library(
              name = "bar_lib",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "lib.cpp",
              ],
            )

            cxx_test(
              name = "bar_test",
              labels = [
                "is_fully_translated",
              ],
              srcs = [
                "test.cpp",
              ],
            )
        """
        )
        result = root.runAudit(["not_foo/BUCK"])

        self.validateAudit({"not_foo/BUCK": expected}, result)
