# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils


class CudaTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs:target_utils.bzl", "target_utils"),
        ("@fbcode_macros//build_defs:cuda.bzl", "cuda"),
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
