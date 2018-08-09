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

import textwrap

import tests.utils


class ModulesTest(tests.utils.TestCase):

    includes = [("@fbcode_macros//build_defs:modules.bzl", "modules")]

    @tests.utils.with_project()
    def test_get_module_name(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                ['modules.get_module_name("fbcode", "base/path", "short-name")']),
            "fbcode_base_path_short_name")

    @tests.utils.with_project()
    def test_get_module_map(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                ['modules.get_module_map("name", {"header1.h": ["private"], "header2.h": {}})']),
            textwrap.dedent(
                """\
                module name {
                  module header1_h {
                    private header "header1.h"
                    export *
                  }
                  module header2_h {
                    header "header2.h"
                    export *
                  }
                }
                """))
