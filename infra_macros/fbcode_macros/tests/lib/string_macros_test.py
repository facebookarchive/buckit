# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class StringMacrosTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:string_macros.bzl", "string_macros")]

    @tests.utils.with_project()
    def test_replacements_work(self, root):
        sample_strings = [
            "$(location @/third-party:project:foo) -- $(exe @/third-party-tools:project:bar)",
            "$(location @/third-party:project:baz) -- $(exe @/third-party-tools:project:bazzz)",
        ]

        commands = [
            'string_macros.convert_blob_with_macros("'
            + sample_strings[0]
            + '", platform="default")',
            'string_macros.convert_blob_with_macros("foo", platform="default")',
            'string_macros.convert_args_with_macros(["{}", "{}", "foo"], platform="default")'.format(
                sample_strings[0], sample_strings[1]
            ),
            (
                "string_macros.convert_env_with_macros("
                '{{"USER": "{}", "HOME": "wheretheheartis"}}, platform="default")'.format(
                    sample_strings[0]
                )
            ),
        ]

        expected = [
            "$(location //third-party-buck/default/build/project:foo) -- $(exe //third-party-buck/default/tools/project:bar)",
            "foo",
            [
                "$(location //third-party-buck/default/build/project:foo) -- $(exe //third-party-buck/default/tools/project:bar)",
                "$(location //third-party-buck/default/build/project:baz) -- $(exe //third-party-buck/default/tools/project:bazzz)",
                "foo",
            ],
            {
                "USER": "$(location //third-party-buck/default/build/project:foo) -- $(exe //third-party-buck/default/tools/project:bar)",
                "HOME": "wheretheheartis",
            },
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
