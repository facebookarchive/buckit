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


class JsNodeModuleExternalTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs:js_node_module_external.bzl", "js_node_module_external")]

    # TODO: Migrate internal integration tests to public dir.

    @tests.utils.with_project()
    def test_parses_with_skylark(self, root):
        self.assertSuccess(
            root.runUnitTests(
                self.includes,
                ['"parsed!"'],
            ),
            "parsed!",
        )
