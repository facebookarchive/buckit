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


class ConfigTest(tests.utils.TestCase):
    @tests.utils.with_project()
    def test_simple_property_fetch(self, root):
        includes = [("@fbcode_macros//build_defs:config.bzl", "config")]
        ret1 = root.run_unittests(
            includes, ["config.get_third_party_buck_directory()"]
        )
        root.update_buckconfig(
            "fbcode", "third_party_buck_directory", "foo/bar"
        )
        ret2 = root.run_unittests(
            includes, ["config.get_third_party_buck_directory()"]
        )

        self.assertSuccess(ret1)
        self.assertSuccess(ret2)
        self.assertEqual("", ret1.debug_lines[0])
        self.assertEqual("foo/bar", ret2.debug_lines[0])
