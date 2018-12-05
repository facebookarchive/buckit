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

    includes = [("@fbcode_macros//build_defs/lib:modules.bzl", "modules")]

    expected_cmd = (
        r"""set -euo pipefail\n"""
        r"""while test ! -r .projectid -a `pwd` != / ; do cd ..; done\n"""
        r"""MODULE_HOME=\"${SRCDIR//$PWD\\//}/\"\'module_header_dir\'\n"""
        r"""args=()\n"""
        r"""args+=($(cxx))\n"""
        r"""args+=($(cxxppflags :foo-helper))\n"""
        r"""args+=($(cxxflags))\n"""
        r"""args+=(\'-fmodules\' \'-Rmodule-build\' \'-fimplicit-module-maps\' \'-fno-builtin-module-map\' \'-fno-implicit-modules\' \'-fmodules-cache-path=/DOES/NOT/EXIST\' \'-Xclang\' \'-fno-modules-global-index\' \'-Wnon-modular-include-in-module\' \'-Xclang\' \'-fno-absolute-module-directory\')\n"""
        r"""args+=(\"-Xclang\" \"-emit-module\")\n"""
        r"""args+=(\"-fmodule-name=\"\'bar\')\n"""
        r"""args+=(\"-x\" \"c++-header\")\n"""
        r"args+=(\"-Xclang\" \"-fno-validate-pch\")\n"
        r"""args+=(-Xclang -fmodules-embed-all-files)\n"""
        r"""args+=(\"-DFB_BUCK_MODULE_HOME=\\\"$MODULE_HOME\\\"\")\n"""
        r"""args+=(\"-I$MODULE_HOME\")\n"""
        r"""args+=(\"$MODULE_HOME/module.modulemap\")\n"""
        r"""args+=(\"-o\" \"-\")\n"""
        r"""for i in \"${!args[@]}\"; do\n"""
        r"""  args[$i]=${args[$i]//$PWD\\//}\n"""
        r"""done\n"""
        r"""function inode() {\n"""
        r"""  echo \"\\$(ls -i \"$MODULE_HOME/module.modulemap\" | awk \'{ print $1 }\')\"\n"""
        r"""}\n"""
        r"""function compile() {\n"""
        r"""  (\"${args[@]}\" 3>&1 1>&2 2>&3 3>&-) 2>\"$TMP\"/module.pcm.tmp \\\n"""
        r"""    | >&2 sed \"s|$MODULE_HOME/|\"\'third-party-buck/something/\'\"|g\"\n"""
        r"""  mv -nT \"$TMP\"/module.pcm.tmp \"$TMP\"/module.pcm\n"""
        r"""  inode > \"$TMP\"/inode.txt\n"""
        r"""}\n"""
        r"""inode > \"$TMP/prev_inode.txt\"\n"""
        r"""compile\n"""
        r"""if ! cmp -s \"$TMP/prev_inode.txt\" \"$TMP/inode.txt\"; then\n"""
        r"""  >&2 echo \"Detected non-determinism building module bar.  Retrying...\"\n"""
        r"""  while ! cmp -s \"$TMP/prev_inode.txt\" \"$TMP/inode.txt\"; do\n"""
        r"""    mv -fT \"$TMP/inode.txt\" \"$TMP/prev_inode.txt\"\n"""
        r"""    mv -fT \"$TMP/module.pcm\" \"$TMP/prev.pcm\"\n"""
        r"""    compile 2>/dev/null\n"""
        r"""  done\n"""
        r"""  ! {\n"""
        r"""    scribe_cat \\\n"""
        r"""      perfpipe_fbcode_buck_clang_module_errors \\\n"""
        r"""      \"{\\\"int\\\": \\\n"""
        r"""          {\\\"time\\\": \\$(date +\"%s\")}, \\\n"""
        r"""        \\\"normal\\\": \\\n"""
        r"""          {\\\"build_target\\\": \\\"//third-party-buck/something:foo\\\", \\\n"""
        r"""           \\\"build_uuid\\\": \\\"$BUCK_BUILD_ID\\\", \\\n"""
        r"""           \\\"gvfs_version\\\": \\\"\\$(cd / && getfattr -L --only-values -n user.gvfs.version mnt/gvfs)\\\", \\\n"""
        r"""           \\\"sandcastle_alias\\\": \\\"${SANDCASTLE_ALIAS:-}\\\", \\\n"""
        r"""           \\\"sanscastle_job_info\\\": \\\"${SANDCASTLE_NONCE:-}/${SANDCASTLE_INSTANCE_ID:-}\\\", \\\n"""
        r"""           \\\"user\\\": \\\"$USER\\\"}}\";\n"""
        r"""  }\n"""
        r"""fi\n"""
        r'''mv -nT \"$TMP/module.pcm\" \"$OUT\"'''
    )

    override_home_cmd = (
        r"""OLD=\"$MODULE_HOME\"\n"""
        r"""VER=\"\\$(echo \"$OLD\" | grep -Po \",v[a-f0-9]{7}(?=__srcs/)\"; true)\"\n"""
        r"""NEW=\"\\$(printf \'third-party-buck/something\' \"$VER\")\"\n"""
        r"""if [ ${#NEW} -gt ${#OLD} ]; then\n"""
        r"""  >&2 echo \"New module home ($NEW) bigger than old one ($OLD)\"\n"""
        r"""  exit 1\n"""
        r"""fi\n"""
        r"""NEW=\"\\$(echo -n \"$NEW\" | sed -e :a -e \"s|^.\\{1,$(expr \"$(echo -n \"$OLD\" | wc -c)\" - 1)\\}$|&/|;ta\")\"\n"""
        r'''sed -i \"s|$OLD|$NEW|g\" \"$OUT\"'''
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
                  explicit module "header1.h" {
                    private header "header1.h"
                    export *
                  }
                  explicit module "header2.h" {
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
            load("@fbcode_macros//build_defs/lib:modules.bzl", "modules")
            modules.gen_tp2_cpp_module(
                name = "foo",
                module_name = "bar",
                header_dir = "",
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
  labels = [
    "is_fully_translated",
  ],
  out = "module.pcm",
  srcs = {{
    "module_header_dir": "",
  }},
)

cxx_library(
  name = "foo-helper",
  exported_preprocessor_flags = [
    "-DFOO",
  ],
  labels = [
    "generated",
    "is_fully_translated",
  ],
  visibility = [
    "//third-party-buck/something:foo",
  ],
)
        """
        ).format(cmd=self.expected_cmd + "\n" + self.override_home_cmd)
        result = root.runAudit(["third-party-buck/something/BUCK"])
        self.validateAudit({"third-party-buck/something/BUCK": expected}, result)

    @tests.utils.with_project(use_python=True, use_skylark=False)
    def test_gen_tp2_cpp_module_parses_py(self, root):
        root.addFile(
            "third-party-buck/something/BUCK",
            textwrap.dedent(
                """
            load("@fbcode_macros//build_defs/lib:modules.bzl", "modules")
            modules.gen_tp2_cpp_module(
                name = "foo",
                module_name = "bar",
                header_dir = "",
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
  labels = [
    "is_fully_translated",
  ],
  out = "module.pcm",
  srcs = {{
    "module_header_dir": "",
  }},
)

cxx_library(
  name = "foo-helper",
  exported_preprocessor_flags = [
    "-DFOO",
  ],
  labels = [
    "generated",
    "is_fully_translated",
  ],
  visibility = [
    "//third-party-buck/something:foo",
  ],
)
        """
        ).format(cmd=self.expected_cmd + "\n" + self.override_home_cmd)
        result = root.runAudit(["third-party-buck/something/BUCK"])
        self.validateAudit({"third-party-buck/something/BUCK": expected}, result)
