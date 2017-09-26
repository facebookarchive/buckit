#!/usr/bin/env python

# Copyright opyright 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from ..macro_lib.convert.thrift_library import ThriftLibraryConverter

from . import utils


class Py3ThriftConverterTest(utils.ConverterTestCase):
    def setUp(self):
        super(Py3ThriftConverterTest, self).setUp()
        self.setup_with_config({}, {})

    def setup_with_config(self, additional_configs, removed_configs):
        self._state = self._create_converter_state(
            additional_configs,
            removed_configs
        )
        self._converter = (
            ThriftLibraryConverter(
                self._state.context,
            )
        )

    def test_cpp2_auto_included(self):
        rules = self._converter.convert(
            'base',
            'name',
            thrift_srcs={'service.thrift': []},
            languages=[
                'py3',
            ]
        )

        for rule in rules:
            if rule.attributes['name'] == "name-cpp2":
                self.assertEqual('cxx_library', rule.type)
                break
        else:
            self.fail('cpp2 thrift language not added for py3 lang target')

    def test_cpp2_options_copy_to_py3_options(self):
        OPTIONS = "BLAHBLAHBLAH"
        rules = self._converter.convert(
            'base',
            'name',
            thrift_srcs={'service.thrift': []},
            languages=['py3', 'cpp2'],
            thrift_cpp2_options=OPTIONS,
        )
        for rule in rules:
            if rule.attributes['name'] == "name-py3-service.thrift":
                self.assertEqual('genrule', rule.type)
                self.assertTrue(OPTIONS in rule.attributes['cmd'])
                break
        else:
            self.fail('failed to find py3 thrift compiler target')
