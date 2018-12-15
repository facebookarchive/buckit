# Copyright 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import operator
import platform

import tests.utils
from tests.utils import dedent


class PythonVersioningTest(tests.utils.TestCase):
    includes = [
        ("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils"),
        ("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party"),
        ("@fbcode_macros//build_defs/lib:python_versioning.bzl", "python_versioning"),
    ]

    setupThirdPartyConfig = True
    setupPlatformOverrides = True

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
                   "build": {{
                        "projects": {{
                            "python": "2.7",
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
                "third_party.get_tp2_project_target('python'), fbcode_platform = 'gcc5')"
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

    @tests.utils.with_project()
    def test_python_version_parses(self, root):
        commands = [
            'python_versioning.python_version("2")',
            'python_versioning.python_version("3")',
            'python_versioning.python_version("4")',
            'python_versioning.python_version("2.7")',
            'python_versioning.python_version("3.7")',
            'python_versioning.python_version("4.7")',
            'python_versioning.python_version("2.7.1")',
            'python_versioning.python_version("3.7.1")',
            'python_versioning.python_version("4.7.1")',
            'python_versioning.python_version("pypy.2")',
            'python_versioning.python_version("pypy.2.7")',
            'python_versioning.python_version("pypy.2.7.1")',
            'python_versioning.python_version("")',
            "python_versioning.python_version(None)",
        ]

        expected = [
            self.struct(version_string="2", flavor="", major=2, minor=0, patchlevel=0),
            self.struct(version_string="3", flavor="", major=3, minor=0, patchlevel=0),
            self.struct(version_string="4", flavor="", major=4, minor=0, patchlevel=0),
            self.struct(
                version_string="2.7", flavor="", major=2, minor=7, patchlevel=0
            ),
            self.struct(
                version_string="3.7", flavor="", major=3, minor=7, patchlevel=0
            ),
            self.struct(
                version_string="4.7", flavor="", major=4, minor=7, patchlevel=0
            ),
            self.struct(
                version_string="2.7.1", flavor="", major=2, minor=7, patchlevel=1
            ),
            self.struct(
                version_string="3.7.1", flavor="", major=3, minor=7, patchlevel=1
            ),
            self.struct(
                version_string="4.7.1", flavor="", major=4, minor=7, patchlevel=1
            ),
            self.struct(
                version_string="pypy.2", flavor="pypy", major=2, minor=0, patchlevel=0
            ),
            self.struct(
                version_string="pypy.2.7", flavor="pypy", major=2, minor=7, patchlevel=0
            ),
            self.struct(
                version_string="pypy.2.7.1",
                flavor="pypy",
                major=2,
                minor=7,
                patchlevel=1,
            ),
            self.struct(version_string="3", flavor="", major=3, minor=0, patchlevel=0),
            self.struct(version_string="3", flavor="", major=3, minor=0, patchlevel=0),
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project(run_buckd=True)
    def test_python_version_fails_with_invalid_version_strings(self, root):
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ['python_versioning.python_version("foo")']
            ),
            "Invalid version string foo provided",
        )
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ['python_versioning.python_version("foo.bar")']
            ),
            "invalid literal for int() with base 10: ",
        )
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ['python_versioning.python_version("foo.1.bar")']
            ),
            "invalid literal for int() with base 10: ",
        )
        self.assertFailureWithMessage(
            root.runUnitTests(
                self.includes, ['python_versioning.python_version("foo.1.2.bar")']
            ),
            "invalid literal for int() with base 10: ",
        )

    @tests.utils.with_project()
    def test_version_supports_flavor(self, root):
        commands = [
            'python_versioning.version_supports_flavor(python_versioning.python_version("3"), "pypy")',
            'python_versioning.version_supports_flavor(python_versioning.python_version("other.3"), "pypy")',
            'python_versioning.version_supports_flavor(python_versioning.python_version("pypy.3"), "pypy")',
            'python_versioning.version_supports_flavor(python_versioning.python_version("broken-pypy.3"), "pypy")',
        ]

        expected = [False, False, True, True]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_constraints_properly_constraint(self, root):
        constraints = [("2", (2, 0, 0)), ("2.5", (2, 5, 0)), ("2.5.0", (2, 5, 0))]
        versions = [
            ("1", (1, 0, 0)),
            ("2", (2, 0, 0)),
            ("4", (4, 0, 0)),
            ("1.0", (1, 0, 0)),
            ("1.5", (1, 5, 0)),
            ("2.0", (2, 0, 0)),
            ("2.5", (2, 5, 0)),
            ("4.0", (4, 0, 0)),
            ("4.5", (4, 5, 0)),
            ("1.0.0", (1, 0, 0)),
            ("1.5.0", (1, 5, 0)),
            ("1.5.5", (1, 5, 5)),
            ("2.0.0", (2, 0, 0)),
            ("2.5.0", (2, 5, 0)),
            ("2.5.5", (2, 5, 5)),
            ("4.0.0", (4, 0, 0)),
            ("4.5.0", (4, 5, 0)),
            ("4.5.5", (4, 5, 5)),
        ]
        ops = {
            "<": operator.lt,
            "<=": operator.le,
            ">": operator.gt,
            ">=": operator.ge,
            "=": operator.eq,
        }
        # Note that this doesn't quite match LooseVersion behavior
        # See docs for details
        all_constraints = [
            (op_txt + constraint_str, version_str, op(version, constraint))
            for op_txt, op in sorted(ops.items())
            for constraint_str, constraint in constraints
            for version_str, version in versions
        ]
        all_constraints.extend(
            [
                ("", "1", False),
                ("", "1.5", False),
                ("", "1.5.5", False),
                (None, "1", False),
                (None, "1.5", False),
                (None, "1.5.5", False),
                ("", "3", True),
                ("", "3.5", True),
                ("", "3.5.5", True),
                (None, "3", True),
                (None, "3.5", True),
                (None, "3.5.5", True),
                (">=foo.1.0.0", "1.0.0", False),
                (">=foo.1.0.0", "foo.1.1.0", True),
            ]
        )
        commands = [
            (
                "python_versioning.constraint_matches("
                "python_versioning.python_version_constraint({}),"
                'python_versioning.python_version("{}")'
                ")"
            ).format("None" if constraint is None else '"' + constraint + '"', version)
            for constraint, version, expected in all_constraints
        ]

        expected = [expected for constraint, version, expected in all_constraints]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_constraints_properly_do_minor_checks(self, root):
        all_constraints = [
            ("2", "2.0", False, True),
            ("2", "2", False, True),
            ("2", "2.5", False, True),
            ("2", "3", False, False),
            ("2", "3.5", False, False),
            ("3", "3.0", False, True),
            ("3", "3", False, True),
            ("3", "3.5", False, True),
            ("3", "4", False, False),
            ("3", "4.5", False, False),
            ("2", "2.0", True, True),
            ("2", "2", True, True),
            ("2", "2.5", True, False),
            ("2", "3", True, False),
            ("2", "3.5", True, False),
            ("3", "3.0", True, True),
            ("3", "3", True, True),
            ("3", "3.5", True, False),
            ("3", "4", True, False),
            ("3", "4.5", True, False),
            ("4.5", "4.2", False, False),
            ("4.5", "4.5", False, True),
            ("4.5", "4.5.1", False, False),
            ("4.5", "4.2", True, False),
            ("4.5", "4.5", True, True),
            ("4.5", "4.5.1", True, True),
            ("4.5.1", "4.2", False, False),
            ("4.5.1", "4.5", False, False),
            ("4.5.1", "4.5.1", False, True),
            ("4.5.1", "4.2", True, False),
            ("4.5.1", "4.5", True, True),
            ("4.5.1", "4.5.1", True, True),
        ]
        commands = [
            (
                "python_versioning.constraint_matches("
                'python_versioning.python_version_constraint("{}"),'
                'python_versioning.python_version("{}"),'
                "check_minor={}"
                ")"
            ).format(constraint, version, check_minor)
            for constraint, version, check_minor, expected in all_constraints
        ]

        expected = [
            expected for constraint, version, check_minor, expected in all_constraints
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)

    @tests.utils.with_project()
    def test_normalizes_constraints(self, root):
        commands = [
            (
                "python_versioning.normalize_constraint("
                'python_versioning.python_version_constraint("4"))'
            ),
            "python_versioning.normalize_constraint(4)",
            'python_versioning.normalize_constraint("4")',
        ]

        expected = [
            self.struct(version_string="4", flavor="", major=4, minor=0, patchlevel=0),
            self.struct(version_string="4", flavor="", major=4, minor=0, patchlevel=0),
            self.struct(version_string="4", flavor="", major=4, minor=0, patchlevel=0),
        ]

        result = root.runUnitTests(self.includes, commands)
        self.assertSuccess(result)
        versions = [constraint.version for constraint in result.debug_lines]
        self.assertEquals(expected, versions)

    @tests.utils.with_project()
    def test_get_all_versions(self, root):
        commands = [
            'python_versioning.get_all_versions("gcc5")',
            "python_versioning.get_all_versions(None)",
        ]

        expected = [
            [
                self.struct(
                    version_string="2.7", flavor="", major=2, minor=7, patchlevel=0
                )
            ],
            [
                self.struct(
                    version_string="2.7", flavor="", major=2, minor=7, patchlevel=0
                ),
                self.struct(
                    version_string="3.7", flavor="", major=3, minor=7, patchlevel=0
                ),
            ],
        ]

        result = root.runUnitTests(self.includes, commands)
        self.assertSuccess(result, *expected)
