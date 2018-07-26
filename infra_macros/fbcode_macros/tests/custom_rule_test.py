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

import os
import platform as _platform

import tests.utils
from tests.utils import dedent


class CustomRuleTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")]

    def _getCopyCommand(self, main_rule, output_name):
        if _platform.system() == "Darwin":
            return (
                'mkdir -p `dirname \\"$OUT\\"` && '
                'ln \\"$(location :{main_rule}-outputs)/{output_name}\\" \\"$OUT\\"'
            ).format(main_rule=main_rule, output_name=output_name)
        else:
            return (
                'mkdir -p `dirname \\"$OUT\\"` && '
                'cp -rlT \\"$(location :{main_rule}-outputs)/{output_name}\\" \\"$OUT\\"'
            ).format(main_rule=main_rule, output_name=output_name)

    @tests.utils.with_project()
    def test_fails_if_output_gen_files_is_wrong_type(self, root):
        root.addFile("BUCK", dedent("""
        load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
        custom_rule(name="foobar", build_script_dep=":ignore", output_gen_files="not a list")
        """))

        result = root.runAudit(["BUCK"])

        self.assertFailureWithMessage(
            result,
            "output_gen_files and output_bin_files must be lists of filenames")

    @tests.utils.with_project()
    def test_fails_if_no_output_gen_files_provided(self, root):
        root.addFile("BUCK", dedent("""
        load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
        custom_rule(name="foobar", build_script_dep=":ignore")
        """))

        result = root.runAudit(["BUCK"])

        self.assertFailureWithMessage(
            result,
            "neither output_gen_files nor output_bin_files were specified")

    @tests.utils.with_project()
    def test_fails_if_build_args_is_wrong_type(self, root):
        root.addFile("BUCK", dedent("""
        load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
        custom_rule(name="foobar", build_script_dep=":ignore", build_args=["arg1", "arg2"])
        """))

        result = root.runAudit(["BUCK"])

        self.assertFailureWithMessage(
            result,
            "build_args must be a string or None")

    @tests.utils.with_project()
    def test_fails_if_two_dots_in_output_gen_files(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(name="foobar", build_script_dep=":ignore", output_gen_files=("../foobar",))
        """))

        result = root.runAudit(["BUCK"])

        self.assertFailureWithMessage(
            result,
            "output file ../foobar cannot contain '..'")

    @tests.utils.with_project()
    def test_fails_if_two_dots_in_output_bin_files(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(name="foobar", build_script_dep=":ignore", output_bin_files=("../foobar",))
        """))

        result = root.runAudit(["BUCK"])

        self.assertFailureWithMessage(
            result,
            "output file ../foobar cannot contain '..'")

    @tests.utils.with_project()
    def test_converts_third_party_paths(self, root):
        # NOTE: Changes:
        # deps are interpolated

        # - srcs are NOT converted
        # - tool paths
        # - build_script_dep
        # - build_args
        # - deps[]
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="@/third-party:proj:some_genrule",
                build_args="--flag $(location @/third-party:boost:data_file)",
                srcs=["@/third-party:thrift/bin:thrift"],
                tools=["protobufs", "cc"],
                output_gen_files=["out1"],
                deps=[
                    "@/third-party:project:straggler",
                    "@/third-party-tools:project:straggler2",
                ],
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS='
            '$(location //third-party-buck/default/tools:protobufs/bin):'
            '$(location //third-party-buck/default/tools:cc/bin) '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH='
            '$GEN_DIR/../../third-party-buck/default/tools/protobufs/bin:'
            '$GEN_DIR/../../third-party-buck/default/tools/cc/bin:'
            '\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //third-party-buck/default/build/proj:some_genrule) '
            '--install_dir=\\"$OUT\\" '
            '--flag '
            '$(location //third-party-buck/default/build/boost:data_file) '
            '# $(location //third-party-buck/default/build/project:straggler) '
            '$(location //third-party-buck/default/tools/project:straggler2)'
        )
        expected = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = False,
              out = "foobar-outputs",
              srcs = [
                "@/third-party:thrift/bin:thrift",
              ],
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_fails_if_tool_rule_does_not_exist(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            load("@fbcode_macros//build_defs:native_rules.bzl", "buck_sh_binary")
            buck_sh_binary(name="main.sh", main="main.sh")
            custom_rule(
                name="foobar",
                build_script_dep="//:main.sh",
                tools=["cc"],
                output_gen_files=["out1"],
            )
        """))
        root.addFile("main.sh", "touch \"$OUT\"; exit 0;", executable=True)

        result = root.run(["buck", "build", "//:foobar"], {}, {})
        self.assertFailureWithMessage(
            result,
            "No build file at third-party-buck/default/tools/BUCK when "
            "resolving target //third-party-buck/default/tools:cc/bin",
            "This error happened while trying to get dependency "
            "'//third-party-buck/default/tools:cc/bin' of target "
            "'//:foobar-outputs'")

    @tests.utils.with_project()
    def test_adds_fbcode_env_var_and_flag_if_not_strict(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                build_args="--flag $(location //:arg_dep)",
                srcs=["//:src1", "//:src2"],
                tools=["protobufs", "cc"],
                deps=[
                    "//:old_dep1",
                    "//:old_dep2",
                ],
                output_gen_files=["out1"],
                strict=False,
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_DIR=$GEN_DIR/../.. '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS='
            '$(location //third-party-buck/default/tools:protobufs/bin):'
            '$(location //third-party-buck/default/tools:cc/bin) '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH='
            '$GEN_DIR/../../third-party-buck/default/tools/protobufs/bin:'
            '$GEN_DIR/../../third-party-buck/default/tools/cc/bin:'
            '\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--fbcode_dir=$GEN_DIR/../.. '
            '--install_dir=\\"$OUT\\" '
            '--flag '
            '$(location //:arg_dep) '
            '# $(location //:old_dep1) '
            '$(location //:old_dep2)'
        )
        expected = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = "''' + expected_cmd + '''",
              noRemote = False,
              out = "foobar-outputs",
              srcs = [
                "//:src1",
                "//:src2",
              ],
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )
        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_handles_defaults(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1"],
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS= '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH=\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--install_dir=\\"$OUT\\"'
        )
        expected = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = False,
              out = "foobar-outputs",
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )
        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_creates_main_rule_as_output_with_only_one_out(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1"],
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS= '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH=\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--install_dir=\\"$OUT\\"'
        )
        expected = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = False,
              out = "foobar-outputs",
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )
        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_creates_main_rule_as_python_lib_with_more_than_one_out(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1","out2"],
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS= '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH=\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--install_dir=\\"$OUT\\"'
        )
        expected = dedent('''
            python_library(
              name = "foobar",
              deps = [
                ":foobar=out1",
                ":foobar=out2",
              ],
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = False,
              out = "foobar-outputs",
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar=out2",
              cmd = "''' + self._getCopyCommand("foobar", "out2") + '''",
              out = "out2",
              visibility = [
                "PUBLIC",
              ],
            )
        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_gets_correct_visibility(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1"],
            )
        """))
        root.addFile("experimental/test/BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1"],
            )
        """))
        root.addFile("other/BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1"],
                visibility=[],
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS= '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH=\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--install_dir=\\"$OUT\\"'
        )
        expected_template = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",{vis}
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = False,
              out = "foobar-outputs",
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",{vis}
            )
        ''')
        default_vis = '\n  visibility = [\n    "PUBLIC",\n  ],'
        experimental_vis = '\n  visibility = [\n    "//experimental/...",\n  ],'
        other_vis = ''

        result = root.runAudit(["BUCK", "experimental/test/BUCK", "other/BUCK"])

        self.validateAudit({
            "BUCK": expected_template.format(vis=default_vis),
            "experimental/test/BUCK": expected_template.format(vis=experimental_vis),
            "other/BUCK": expected_template.format(vis=other_vis),
        }, result)

    @tests.utils.with_project()
    def test_passes_no_remote(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                output_gen_files=["out1"],
                no_remote=True,
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS= '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH=\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--install_dir=\\"$OUT\\"'
        )
        expected = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = True,
              out = "foobar-outputs",
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )
        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_copy_genrule_output_file_creates_correct_rule(self, root):
        root.addFile("other/BUCK", dedent("""
            genrule(
                name="main",
                cmd='mkdir -p "$OUT" && echo 1 > $OUT/out1; echo 2 > $OUT/out2',
                out="outdir",
                visibility=["PUBLIC"],
            )
        """))
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "copy_genrule_output_file")
            copy_genrule_output_file(
                name_prefix="main",
                genrule_target="//other:main",
                filename="out1",
                visibility=["PUBLIC"],
            )
        """))

        result = root.run(["buck", "build", "--show-output", "//:"], {}, {})

        self.assertSuccess(result)
        outputs = {}
        for line in result.stdout.strip().split("\n"):
            parts = line.split(None, 1)
            outputs[parts[0]] = os.path.join(root.fullPath(), parts[1])

        self.assertTrue(os.path.exists(outputs["//:main=out1"]))
        with open(outputs["//:main=out1"]) as fin:
            self.assertEqual("1", fin.read().decode('utf-8').strip())

    @tests.utils.with_project()
    def test_output_can_be_used(self, root):
        # Quick integration test
        root.addFile("gen.sh", dedent("""
            cat > $INSTALL_DIR/main.h <<EOF
            #pragma once
            struct Printer { static void print(); };
            EOF
            cat > $INSTALL_DIR/main.cpp <<EOF
            #include "main.h"
            #include <iostream>
            using namespace std;
            void Printer::print() { cout << "Hello, world" << endl; }
            int main() { Printer::print(); return 0; }
            EOF
        """), executable=True)
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            load("@fbcode_macros//build_defs:native_rules.bzl", "buck_sh_binary")
            buck_sh_binary(name = "gen.sh", main = "gen.sh")
            custom_rule(
                name = "foo",
                build_script_dep = ":gen.sh",
                output_gen_files = ["main.h", "main.cpp"],
            )
            cxx_binary(
                name = "main",
                srcs = [":foo=main.cpp"],
                headers = [":foo=main.h"],
            )
        """))

        result = root.run(["buck", "run", "//:main"], {}, {})

        self.assertSuccess(result)
        self.assertEquals("Hello, world", result.stdout.decode('utf-8').strip())

    @tests.utils.with_project(use_skylark=False)
    def test_build_args_work_with_unicode_strings(self, root):
        root.addFile("BUCK", dedent("""
            load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
            custom_rule(
                name="foobar",
                build_script_dep="//:main_script",
                build_args=u"foo",
                output_gen_files=["out1"],
                no_remote=True,
            )
        """))
        expected_cmd = (
            'mkdir -p \\"$OUT\\" && '
            'env '
            'BUCK_PLATFORM=default-gcc '
            'FBCODE_BUILD_MODE=dev '
            'FBCODE_BUILD_TOOL=buck '
            'FBCODE_PLATFORM=default '
            'FBCODE_THIRD_PARTY_TOOLS= '
            'INSTALL_DIR=\\"$OUT\\" '
            'PATH=\\"$PATH\\" '
            'SRCDIR=\\"$SRCDIR\\" '
            '$(exe //:main_script) '
            '--install_dir=\\"$OUT\\" '
            'foo'
        )
        expected = dedent('''
            genrule(
              name = "foobar",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )

            genrule(
              name = "foobar-outputs",
              cmd = \"''' + expected_cmd + '''\",
              noRemote = True,
              out = "foobar-outputs",
            )

            genrule(
              name = "foobar=out1",
              cmd = "''' + self._getCopyCommand("foobar", "out1") + '''",
              out = "out1",
              visibility = [
                "PUBLIC",
              ],
            )
        ''')

        result = root.runAudit(["BUCK"])

        self.validateAudit({"BUCK": expected}, result)
