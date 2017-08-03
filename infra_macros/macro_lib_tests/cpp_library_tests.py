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

from ..macro_lib.convert.cpp import CppConverter

from . import utils


class CppLibraryConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(CppLibraryConverterTest, self).setUp()
        self._state = self._create_converter_state()
        self._converter = (
            CppConverter(
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
