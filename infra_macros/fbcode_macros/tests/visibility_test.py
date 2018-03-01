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

import tests.utils


class VisibilityTest(tests.utils.TestCase):
    maxDiff = None
    includes = [
        (
            "@fbcode_macros//build_defs:visibility.bzl",
            "get_visibility",
            "get_visibility_for_base_path"
        )
    ]

    @tests.utils.with_project()
    def test_returns_default_visibility_or_original_visibility(self, root):
        statements = [
            'get_visibility(None, "foo")',
            'get_visibility(["//..."], "foo")',
        ]
        result = root.run_unittests(self.includes, statements)
        self.assertSuccess(result, ["PUBLIC"], ["//..."])

    @tests.utils.with_project()
    def test_returns_default_visibility_inside_of_experimental(self, root):
        statements = [
            'get_visibility(None, "all_lua")',
            'get_visibility(None, "foo")',
            'get_visibility(["//..."], "all_lua")',
            'get_visibility(["//..."], "foo")',
        ]
        result = root.run_unittests(
            self.includes,
            statements,
            buckfile="experimental/deeplearning/BUCK")
        self.assertSuccess(
            result,
            ["PUBLIC"],
            ["//experimental/..."],
            ["//..."],
            ["//experimental/..."])

    @tests.utils.with_project()
    def test_returns_experimental_visibility_for_experimental_things(self, root):
        statements = [
            ('get_visibility_for_base_path(None, "other", '
                '"experimental/deeplearning/ntt/detection_caffe2/lib")'),
            ('get_visibility_for_base_path(None, "lib", '
                '"experimental/deeplearning/ntt/detection_caffe2/lib")'),
            ('get_visibility_for_base_path(["//..."], "lib", '
                '"experimental/deeplearning/ntt/detection_caffe2/lib")'),
            'get_visibility_for_base_path(None, "target", "other_dir")',
            'get_visibility_for_base_path(["//..."], "target", "target_dir")',
        ]
        result = root.run_unittests(self.includes, statements)
        self.assertSuccess(result, ["//experimental/..."], ["PUBLIC"],
                           ["//..."], ["PUBLIC"], ["//..."])
