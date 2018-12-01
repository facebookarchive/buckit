# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class CudaTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils"),
        ("@fbcode_macros//build_defs/lib:cuda.bzl", "cuda"),
    ]

    @tests.utils.with_project()
    def test_cuda_src_methods(self, root):
        commands = [
            'cuda.has_cuda_dep([target_utils.RootRuleTarget("foo", "bar")])',
            'cuda.has_cuda_dep([target_utils.ThirdPartyRuleTarget("foo", "bar")])',
            'cuda.has_cuda_dep([target_utils.ThirdPartyRuleTarget("cuda", "bar")])',
            'cuda.is_cuda_src("foo/bar.h")',
            'cuda.is_cuda_src(":foo=cuda.cu")',
            'cuda.is_cuda_src(":foo")',
            'cuda.is_cuda_src("//foo:bar")',
        ]
        expected = [False, False, True, False, True, False, False]
        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_strip_cuda_properties(self, root):
        commands = [
            dedent(
                """
            cuda.strip_cuda_properties(
                base_path="caffe2",
                name="bar",
                compiler_flags=["-DUSE_CUDNN=1", "-DUSE_CUDNN", "-DFOO1"],
                preprocessor_flags=["-DUSE_CUDNN=1", "-DUSE_CUDNN", "-DFOO2"],
                propagated_pp_flags=["-DUSE_CUDNN=1", "-DUSE_CUDNN", "-DFOO3"],
                nvcc_flags=["-DUSE_CUDNN=1", "-DUSE_CUDNN", "-DFOO4"],
                arch_compiler_flags={
                    "linux": ["-DUSE_CUDNN=1", "-DUSE_CUDNN", "-DFOO5"],
                },
                arch_preprocessor_flags={
                    "linux": ["-DUSE_CUDNN=1", "-DUSE_CUDNN", "-DFOO6"],
                },
                srcs=[
                    "foo/bar.cu",
                    "foo/bar.cc",
                    "caffe2/foo/cudnn.cc",
                    "torch/csrc/distributed/c10d/ddp.cpp",
                ],
            )
            """
            )
        ]

        expected = self.struct(
            srcs=["foo/bar.cc"],
            cuda_srcs=[
                "foo/bar.cu",
                "caffe2/foo/cudnn.cc",
                "torch/csrc/distributed/c10d/ddp.cpp",
            ],
            compiler_flags=["-DFOO1"],
            preprocessor_flags=["-DFOO2"],
            propagated_pp_flags=["-DFOO3"],
            nvcc_flags=["-DFOO4"],
            arch_compiler_flags={"linux": ["-DFOO5"]},
            arch_preprocessor_flags={"linux": ["-DFOO6"]},
        )

        self.assertSuccess(root.runUnitTests(self.includes, commands), expected)
