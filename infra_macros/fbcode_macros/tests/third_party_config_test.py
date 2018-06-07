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


class ThirdPartyConfigTest(tests.utils.TestCase):
    includes = [
        (
            "@fbcode_macros//build_defs:third_party_config.bzl",
            "third_party_config"
        )
    ]
    setupPlatformOverrides = False

    @tests.utils.with_project()
    def test_imports_third_party_lib(self, root):
        statements = [
            "len(third_party_config) > 0",
            (
                'all(["architecture" in platform for platform in '
                'third_party_config["platforms"].values()])'
            ),
            (
                'all(["tools" in platform for platform in '
                'third_party_config["platforms"].values()])'
            ),
            (
                'all([type(platform["tools"]) == type({}) for platform in '
                'third_party_config["platforms"].values()])'
            ),
        ]
        expected = [True for statement in statements]
        result = root.run_unittests(self.includes, statements)
        self.assertSuccess(result)
        self.assertEquals(expected, result.debug_lines)
