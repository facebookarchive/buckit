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


class CommonPathTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:common_paths.bzl",
                 "get_buck_out_path", "get_gen_path")]

    @tests.utils.with_project()
    def test_returns_correct_paths_with_default(self, root):
        result = root.run_unittests(
            self.includes,
            ["get_buck_out_path()", "get_gen_path()"],
        )
        self.assertSuccess(result, "buck-out", "buck-out/gen")

    @tests.utils.with_project()
    def test_returns_correct_paths_with_config(self, root):
        root.update_buckconfig("project", "buck_out", "buck-out/dev")
        result = root.run_unittests(
            self.includes,
            ["get_buck_out_path()", "get_gen_path()"],
        )
        self.assertSuccess(result, "buck-out/dev", "buck-out/dev/gen")
