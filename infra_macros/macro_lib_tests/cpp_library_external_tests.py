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


class CppLibraryExternalConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(CppLibraryExternalConverterTest, self).setUp()
        try:
            self._state = self._create_converter_state()
            self._cpp = (
                self._state.parser.load_include(
                    'tools/build/buck/infra_macros/macro_lib/convert/cpp_library_external.py'))
            self._converter = (
                self._cpp.CppLibraryExternalConverter(
                    self._state.context,
                    'cpp_library_external'))
        except:
            super(CppLibraryExternalConverterTest, self).tearDown()
            raise

    def test_get_lib_path(self):
        self.assertEquals(
            self._converter.get_lib_path(
                'base/path',
                'foo',
                'lib',
                'bar',
                '.so'),
            'base/path/lib/libbar.so')
        self.assertEquals(
            self._converter.get_lib_path('base/path', 'foo', 'lib', None, '.a'),
            'base/path/lib/libfoo.a')
