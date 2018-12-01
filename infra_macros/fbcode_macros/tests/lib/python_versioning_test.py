# Copyright 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import platform

import tests.utils
from tests.utils import dedent


class PythonVersioningTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils"),
        ("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party"),
        ("@fbcode_macros//build_defs/lib:python_versioning.bzl", "python_versioning"),
    ]

    setupThirdPartyConfig = False
    setupPlatformOverrides = False

    current_arch = platform.machine()
    other_arch = "x86_64" if current_arch == "aarch64" else "aarch64"

    third_party_config = dedent(
        """\
        third_party_config = {{
            "platforms": {{
                "gcc5": {{
                    "architecture": "{current_arch}",
                    "tools": {{
                        "projects": {{
                            "ghc": "8.0.2",
                        }},
                    }},
                    "build":  {{
                        "projects": {{
                            "ghc": "8.0.2",
                            "python": [
                                      ("2.7", "2.7"),
                                      ("a.2.7", "a.2.7"),
                                      ("ba.2.7", "ba.2.7"),
                                      ("c.2.7", "c.2.7"),
                            ],
                        }}
                    }}
                }},
                "gcc7": {{
                    "architecture": "{current_arch}",
                    "tools": {{
                        "projects": {{
                            "ghc": "8.0.2",
                        }},
                    }},
                }},
            }},
            "version_universes": [
                {{"python": "2.7", "openssl": "1.0.2"}},
                {{"python": "3.7", "openssl": "1.0.2"}},
                {{"python": "2.7", "openssl": "1.1.0"}},
                {{"python": "3.7", "openssl": "1.1.0"}},
            ],
        }}
    """.format(
            current_arch=current_arch, other_arch=other_arch
        )
    )

    platform_overrides = dedent(
        """\
        platform_overrides = {
            "fbcode": {
                "foo/bar": ["gcc7"],
                "foo": ["gcc5"],
            },
        }
        """
    )

    @tests.utils.with_project()
    def test_add_py_flavor_versions(self, root):
        # Setup mock environment:
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", self.third_party_config
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", self.platform_overrides
        )
        # Obtain the Python project label:
        result = root.runUnitTests(
            self.includes,
            [
                "target_utils.target_to_label("
                "third_party.get_tp2_project_target('python'), 'gcc5')"
            ],
        )
        self.assertSuccess(result)
        label = result.debug_lines[0]
        # Test proper:
        tcs = [
            "None",
            "[]",
            "[({}, {})]",
            "[({'a': '1'}, {'f/b': 'f/c/b'})]",
            "[({{'{}': '2.7'}},  {{}})]".format(label),
            "[({{'{0}': 'a.2.7'}},  {{'foo/src.py': 'foo/a/src.py'}}),"
            " ({{'{0}': 'c.2.7'}}, {{'foo/src.py': 'foo/c/src.py'}})]".format(label),
        ]
        expected = [
            None,
            [],
            [({}, {})],
            [({"a": "1"}, {"f/b": "f/c/b"})],
            [
                ({label: "2.7"}, {}),
                [{label: "a.2.7"}, {}],
                [{label: "ba.2.7"}, {}],
                [{label: "c.2.7"}, {}],
            ],
            [
                ({label: "a.2.7"}, {"foo/src.py": "foo/a/src.py"}),
                ({label: "c.2.7"}, {"foo/src.py": "foo/c/src.py"}),
                [{label: "ba.2.7"}, {"foo/src.py": "foo/a/src.py"}],
            ],
        ]
        statements = [
            "python_versioning.add_flavored_versions({})".format(item) for item in tcs
        ]
        result = root.runUnitTests(self.includes, statements)
        self.assertSuccess(result, *expected)
