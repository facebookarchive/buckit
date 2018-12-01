# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import, division, print_function, unicode_literals

import tests.utils
from tests.utils import dedent


class AllocatorsTest(tests.utils.TestCase):
    includes = [("@fbcode_macros//build_defs/lib:allocators.bzl", "allocators")]

    @tests.utils.with_project()
    def test_get_allocator_methods_work(self, root):
        config = {
            "malloc": [],
            "jemalloc": ["jemalloc//jemalloc:jemalloc"],
            "jemalloc_debug": ["jemalloc//jemalloc:jemalloc_debug"],
            "tcmalloc": ["tcmalloc//tcmalloc:tcmalloc"],
        }
        root.updateBuckconfig("fbcode", "default_allocator", "jemalloc_debug")
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/allocator_targets.bzl",
            "allocator_targets = {}".format(repr(config).replace("u'", "'")),
        )

        commands = [
            "allocators.get_default_allocator()",
            "allocators.get_allocators()",
            'allocators.get_allocator_deps("jemalloc")',
            "allocators.normalize_allocator(None)",
            'allocators.normalize_allocator("jemalloc")',
        ]

        expected = [
            "jemalloc_debug",
            config,
            [self.rule_target("jemalloc", "jemalloc", "jemalloc")],
            "jemalloc_debug",
            "jemalloc",
        ]

        self.assertSuccess(root.runUnitTests(self.includes, commands), *expected)
