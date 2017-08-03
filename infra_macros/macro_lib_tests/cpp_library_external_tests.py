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

from ..macro_lib.convert.cpp_library_external import CppLibraryExternalConverter

from . import utils


class CppLibraryExternalConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(CppLibraryExternalConverterTest, self).setUp()
        self._state = self._create_converter_state()
        self._converter = (
            CppLibraryExternalConverter(
                self._state.context,
                'cpp_library_external'))

    def test_get_solib_path(self):
        self.assertEquals(
            self._converter.get_solib_path('base/path', 'foo', 'lib', 'bar'),
            'base/path/lib/libbar.so')
        self.assertEquals(
            self._converter.get_solib_path('base/path', 'foo', 'lib', None),
            'base/path/lib/libfoo.so')
