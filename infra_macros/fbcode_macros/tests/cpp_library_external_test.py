# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import os

import tests.utils
from tests.utils import dedent


class CppLibraryExternalTest(tests.utils.TestCase):
    module_cmd = (
        r"""set -euo pipefail\n"""
        r"""while test ! -r .projectid -a `pwd` != / ; do cd ..; done\n"""
        r"""MODULE_HOME=\"${SRCDIR//$PWD\\//}/\"\'module_header_dir\'\n"""
        r"""args=()\n"""
        r"""args+=($(cxx))\n"""
        r"""args+=($(cxxppflags :MagickCore-module-helper))\n"""
        r"""args+=($(cxxflags))\n"""
        r"""args+=(\'-fmodules\' \'-Rmodule-build\' \'-fimplicit-module-maps\' \'-fno-builtin-module-map\' \'-fno-implicit-modules\' \'-fmodules-cache-path=/DOES/NOT/EXIST\' \'-Xclang\' \'-fno-modules-global-index\' \'-Wnon-modular-include-in-module\' \'-Xclang\' \'-fno-absolute-module-directory\')\n"""
        r"""args+=(\"-Xclang\" \"-emit-module\")\n"""
        r"""args+=(\"-fmodule-name=\"\'third-party//ImageMagick:MagickCore\')\n"""
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
        r"""    | >&2 sed \"s|$MODULE_HOME/|\"\'third-party-buck/gcc5/build/ImageMagick/include/ImageMagick/\'\"|g\"\n"""
        r"""  mv -nT \"$TMP\"/module.pcm.tmp \"$TMP\"/module.pcm\n"""
        r"""  inode > \"$TMP\"/inode.txt\n"""
        r"""}\n"""
        r"""inode > \"$TMP/prev_inode.txt\"\n"""
        r"""compile\n"""
        r"""if ! cmp -s \"$TMP/prev_inode.txt\" \"$TMP/inode.txt\"; then\n"""
        r"""  >&2 echo \"Detected non-determinism building module third-party//ImageMagick:MagickCore.  Retrying...\"\n"""
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
        r"""          {\\\"build_target\\\": \\\"//third-party-buck/gcc5/build/ImageMagick:MagickCore-module\\\", \\\n"""
        r"""           \\\"build_uuid\\\": \\\"$BUCK_BUILD_ID\\\", \\\n"""
        r"""           \\\"gvfs_version\\\": \\\"\\$(cd / && getfattr -L --only-values -n user.gvfs.version mnt/gvfs)\\\", \\\n"""
        r"""           \\\"sandcastle_alias\\\": \\\"${SANDCASTLE_ALIAS:-}\\\", \\\n"""
        r"""           \\\"sanscastle_job_info\\\": \\\"${SANDCASTLE_NONCE:-}/${SANDCASTLE_INSTANCE_ID:-}\\\", \\\n"""
        r"""           \\\"user\\\": \\\"$USER\\\"}}\";\n"""
        r"""  }\n"""
        r"""fi\n"""
        r"""mv -nT \"$TMP/module.pcm\" \"$OUT\"\n"""
        r"""OLD=\"$MODULE_HOME\"\n"""
        r"""VER=\"\\$(echo \"$OLD\" | grep -Po \",v[a-f0-9]{7}(?=__srcs/)\"; true)\"\n"""
        r"""NEW=\"\\$(printf \'third-party-buck/gcc5/build/ImageMagick/include/ImageMagick\' \"$VER\")\"\n"""
        r"""if [ ${#NEW} -gt ${#OLD} ]; then\n"""
        r"""  >&2 echo \"New module home ($NEW) bigger than old one ($OLD)\"\n"""
        r"""  exit 1\n"""
        r"""fi\n"""
        r"""NEW=\"\\$(echo -n \"$NEW\" | sed -e :a -e \"s|^.\\{1,$(expr \"$(echo -n \"$OLD\" | wc -c)\" - 1)\\}$|&/|;ta\")\"\n"""
        r'''sed -i \"s|$OLD|$NEW|g\" \"$OUT\"'''
    )

    @tests.utils.with_project()
    def test_cpp_library_external_parses(self, root):
        buckfile = "third-party-buck/gcc5/build/ImageMagick/BUCK"
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:cpp_library_external.bzl", "cpp_library_external")
        cpp_library_external(
            name = "MagickCore",
            include_dir = [
                "include/ImageMagick",
            ],
            propagated_pp_flags = [
                "-DMAGICKCORE_ARG1=VALUE1",
                "-DMAGICKCORE_ARG2=VALUE2",
            ],
            shared_lib = "lib/libMagickCore.so",
            soname = "libMagickCore.1.2.3.so",
            static_lib = "lib/libMagickCore.a",
            static_pic_lib = "lib/libMagickCore_pic.a",
            external_deps = [
                ("bzip2", None, "bz2"),
                ("glibc", None, "dl"),
            ],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                prebuilt_cxx_library(
                  name = "MagickCore",
                  exported_deps = [
                    "//third-party-buck/gcc5/build/ImageMagick:__project__",
                    "//third-party-buck/gcc5/build/bzip2:bz2",
                    "//third-party-buck/gcc5/build/glibc:dl",
                  ],
                  exported_lang_preprocessor_flags = {
                  },
                  exported_linker_flags = [
                    "-Wl,--no-as-needed",
                  ],
                  exported_preprocessor_flags = [
                    "-DMAGICKCORE_ARG1=VALUE1",
                    "-DMAGICKCORE_ARG2=VALUE2",
                  ],
                  header_dirs = [
                    "include/ImageMagick",
                  ],
                  header_only = False,
                  labels = [
                    "is_fully_translated",
                  ],
                  link_without_soname = False,
                  shared_lib = "lib/libMagickCore.so",
                  soname = "libMagickCore.1.2.3.so",
                  static_lib = "lib/libMagickCore.a",
                  static_pic_lib = "lib/libMagickCore_pic.a",
                  visibility = [
                    "PUBLIC",
                  ],
                )
                """
            )
        }

        self.validateAudit(expected, root.runAudit([buckfile]))

    @tests.utils.with_project()
    def test_cpp_library_external_parses_with_modules(self, root):
        package = os.path.join("third-party-buck", "gcc5", "build", "ImageMagick")
        buckfile = os.path.join(package, "BUCK")
        root.updateBuckconfig("cxx", "modules", "true")
        root.updateBuckconfig("fbcode", "global_compiler", "clang")

        root.addFile(
            os.path.join(package, "include", "ImageMagick", "module.modulemap"), ""
        )
        root.addFile(
            buckfile,
            dedent(
                """
        load("@fbcode_macros//build_defs:cpp_library_external.bzl", "cpp_library_external")
        cpp_library_external(
            name = "MagickCore",
            include_dir = [
                "include/ImageMagick",
            ],
            propagated_pp_flags = [
                "-DMAGICKCORE_ARG1=VALUE1",
                "-DMAGICKCORE_ARG2=VALUE2",
            ],
            shared_lib = "lib/libMagickCore.so",
            soname = "libMagickCore.1.2.3.so",
            static_lib = "lib/libMagickCore.a",
            static_pic_lib = "lib/libMagickCore_pic.a",
            external_deps = [
                ("bzip2", None, "bz2"),
                ("glibc", None, "dl"),
            ],
        )
        """
            ),
        )

        expected = {
            buckfile: dedent(
                r"""
                prebuilt_cxx_library(
                  name = "MagickCore",
                  exported_deps = [
                    "//third-party-buck/gcc5/build/ImageMagick:__project__",
                    "//third-party-buck/gcc5/build/bzip2:bz2",
                    "//third-party-buck/gcc5/build/glibc:dl",
                  ],
                  exported_lang_preprocessor_flags = {{
                    "cxx": [
                      "-fmodule-file=third-party//ImageMagick:MagickCore=$(location :MagickCore-module)",
                    ],
                  }},
                  exported_linker_flags = [
                    "-Wl,--no-as-needed",
                  ],
                  exported_preprocessor_flags = [
                    "-DMAGICKCORE_ARG1=VALUE1",
                    "-DMAGICKCORE_ARG2=VALUE2",
                  ],
                  header_dirs = [
                    "include/ImageMagick",
                  ],
                  header_only = False,
                  labels = [
                    "is_fully_translated",
                  ],
                  link_without_soname = False,
                  shared_lib = "lib/libMagickCore.so",
                  soname = "libMagickCore.1.2.3.so",
                  static_lib = "lib/libMagickCore.a",
                  static_pic_lib = "lib/libMagickCore_pic.a",
                  visibility = [
                    "PUBLIC",
                  ],
                )

                cxx_genrule(
                  name = "MagickCore-module",
                  cmd = "{module_cmd}",
                  labels = [
                    "generated",
                    "is_fully_translated",
                  ],
                  out = "module.pcm",
                  srcs = {{
                    "module_header_dir": "include/ImageMagick",
                  }},
                  visibility = [
                    "//third-party-buck/gcc5/build/ImageMagick:MagickCore",
                  ],
                )

                cxx_library(
                  name = "MagickCore-module-helper",
                  default_platform = "gcc5",
                  defaults = {{
                    "platform": "gcc5",
                  }},
                  exported_deps = [
                    "//third-party-buck/gcc5/build/ImageMagick:__project__",
                    "//third-party-buck/gcc5/build/bzip2:bz2",
                    "//third-party-buck/gcc5/build/glibc:dl",
                  ],
                  exported_preprocessor_flags = [
                    "-DMAGICKCORE_ARG1=VALUE1",
                    "-DMAGICKCORE_ARG2=VALUE2",
                  ],
                  labels = [
                    "generated",
                    "is_fully_translated",
                  ],
                  visibility = [
                    "//third-party-buck/gcc5/build/ImageMagick:MagickCore-module",
                  ],
                )
                """
            ).format(module_cmd=self.module_cmd)
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
