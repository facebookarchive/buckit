#!/usr/bin/env python2

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

from . import utils

import mock


class CppLibraryConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(CppLibraryConverterTest, self).setUp()
        try:
            self.setup_with_config({}, {})
        except:
            super(CppLibraryConverterTest, self).tearDown()
            raise

    def setup_with_config(self, additional_configs, removed_configs):
        self._state = self._create_converter_state(
            additional_configs,
            removed_configs)
        self._cpp = (
            self._state.parser.load_include(
                'tools/build/buck/infra_macros/macro_lib/convert/cpp.py'))
        self._converter = (
            self._cpp.CppConverter(
                self._state.context,
                'cpp_library'))

    def test_exclude_from_auto_pch(self):
        self.assertFalse(
            self._converter.exclude_from_auto_pch('@/test', 'path'))
        self.assertFalse(
            self._converter.exclude_from_auto_pch('//test', 'path'))
        self.assertFalse(
            self._converter.exclude_from_auto_pch('test//test', 'path'))
        self.assertFalse(
            self._converter.exclude_from_auto_pch('@/exclude2', 'path'))
        self.assertFalse(
            self._converter.exclude_from_auto_pch('//exclude2', 'path'))
        self.assertFalse(
            self._converter.exclude_from_auto_pch('exclude2//exclude2', 'path'))

        self.assertTrue(
            self._converter.exclude_from_auto_pch('@/exclude', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch('//exclude', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch('exclude//exclude', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch('@/exclude/dir1', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch('//exclude/dir1', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                'exclude//exclude/dir1', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                '@/exclude/dir1/dir2', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                '//exclude/dir1/dir2', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                'exclude//exclude/dir1/dir2', 'path'))

        self.assertTrue(
            self._converter.exclude_from_auto_pch('@/exclude2/subdir', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch('//exclude2/subdir', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                'exclude2//exclude2/subdir', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                '@/exclude2/subdir/dir2', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                '//exclude2/subdir/dir2', 'path'))
        self.assertTrue(
            self._converter.exclude_from_auto_pch(
                'exclude2//exclude2/subdir/dir2', 'path'))

    def test_does_not_allow_unknown_oses(self):
        with self.assertRaises(KeyError):
            with mock.patch('platform.system', return_value='blargl'):
                self.setup_with_config({('fbcode', 'os_family'): 'bad_stuff'}, {})
                self._converter.convert(
                    'base',
                    'name',
                    srcs=["Lib.cpp"],
                    headers=["Lib.h"],
                    deps=[],
                    external_deps=[('glog', None, 'glog')],
                    auto_headers=None,
                    os_deps=[
                        ('invalid_os', ['@/test:target2']),
                    ],
                )

    def test_drops_targets_for_other_oses(self):
        self.setup_with_config({('fbcode', 'os_family'): 'mac'}, {})
        rules = self._converter.convert(
            'base',
            'name',
            srcs=["Lib.cpp"],
            headers=["Lib.h"],
            deps=[],
            external_deps=[('glog', None, 'glog')],
            auto_headers=None,
            os_deps=[
                ('mac', ['@/test:target2']),
                ('linux', ['@/test:target3']),
            ],
        )

        self.assertEqual(1, len(rules))
        self.assertEqual('cxx_library', rules[0].type)
        attrs = rules[0].attributes
        deps = attrs.get('exported_deps')
        self.assertIsNotNone(deps)
        self.assertEqual(1, len(deps))
        self.assertEqual(['//test:target2'], deps)

    def test_passes_os_linker_flags_through_with_right_platform(self):
        self.setup_with_config({('fbcode', 'os_family'): 'mac'}, {})
        rules = self._converter.convert(
            'base',
            'name',
            srcs=["Lib.cpp"],
            headers=["Lib.h"],
            deps=[],
            external_deps=[('glog', None, 'glog')],
            auto_headers=None,
            os_linker_flags=[
                ('mac', ['-framework', 'CoreServices']),
                ('linux', [])
            ],
            linker_flags=['-rpath,/tmp'],
        )

        self.assertEqual(1, len(rules))
        self.assertEqual('cxx_library', rules[0].type)
        attrs = rules[0].attributes
        flags = attrs.get('exported_linker_flags')
        self.assertIsNotNone(flags)
        self.assertEqual(4, len(flags))
        self.assertEqual(
            [
                '-Xlinker',
                '-rpath,/tmp',
                '-framework',
                'CoreServices'
            ],
            flags)

        # Make sure it toggles for other oses
        self.setup_with_config({('fbcode', 'os_family'): 'linux'}, {})
        rules = self._converter.convert(
            'base',
            'name',
            srcs=["Lib.cpp"],
            headers=["Lib.h"],
            deps=[],
            external_deps=[('glog', None, 'glog')],
            auto_headers=None,
            os_linker_flags=[
                ('mac', ['-framework', 'CoreServices']),
                ('linux', ['-testing', 'flag'])
            ],
            linker_flags=['-rpath,/tmp'],
        )

        self.assertEqual(1, len(rules))
        self.assertEqual('cxx_library', rules[0].type)
        attrs = rules[0].attributes
        flags = attrs.get('exported_linker_flags')
        self.assertIsNotNone(flags)
        self.assertEqual(4, len(flags))
        self.assertEqual(
            [
                '-Xlinker',
                '-rpath,/tmp',
                '-testing',
                'flag'
            ],
            flags)
