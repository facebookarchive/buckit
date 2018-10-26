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
        r"""args=()\n"""
        r"""args+=($(cxx))\n"""
        r"""args+=($(cxxppflags :MagickCore-module-helper))\n"""
        r"""args+=($(cxxflags))\n"""
        r"""args+=(\'-fmodules\' \'-Rmodule-build\' \'-fimplicit-module-maps\' \'-fno-builtin-module-map\' \'-fno-implicit-modules\' \'-fmodules-cache-path=/DOES/NOT/EXIST\' \'-Xclang\' \'-fno-modules-global-index\' \'-Wnon-modular-include-in-module\' \'-Xclang\' \'-fno-absolute-module-directory\')\n"""
        r"""args+=(\"-Xclang\" \"-emit-module\")\n"""
        r"""args+=(\"-fmodule-name=\"\'third-party//ImageMagick:MagickCore\')\n"""
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
            + r" | >&2 sed \"s|${SRCDIR//$PWD\\//}/module_headers/|third-party-buck/gcc5/build/ImageMagick/include/ImageMagick/|g\"\n"
        )
        + r"mv -nT \"$OUT\".tmp \"$OUT\""
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
                  ],
                  out = "module.pcm",
                  srcs = {{
                    "module_headers": "include/ImageMagick",
                  }},
                  visibility = [
                    "//third-party-buck/gcc5/build/ImageMagick:MagickCore",
                  ],
                )

                cxx_library(
                  name = "MagickCore-module-helper",
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
                  ],
                  visibility = [
                    "//third-party-buck/gcc5/build/ImageMagick:MagickCore-module",
                  ],
                )
                """
            ).format(module_cmd=self.module_cmd)
        }

        self.validateAudit(expected, root.runAudit([buckfile]))
