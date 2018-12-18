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

from . import utils
from tools.build.buck.parser import BuildFileContext


class Py3ThriftConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(Py3ThriftConverterTest, self).setUp()
        try:
            self.setup_with_config({}, {})
        except Exception:
            super(Py3ThriftConverterTest, self).tearDown()
            raise

    def setup_with_config(self, additional_configs, removed_configs):
        self._state = self._create_converter_state(
            additional_configs,
            removed_configs
        )
        self._thrift = (
            self._state.parser.load_include(
                'tools/build/buck/infra_macros/macro_lib/convert/thrift_library.py'))
        self._converter = (
            self._thrift.ThriftLibraryConverter()
        )

    def test_cpp2_auto_included(self):
        with self._state.parser._with_stacked_build_env(BuildFileContext("base")):
            self._converter.convert(
                'base',
                'name',
                thrift_srcs={'service.thrift': []},
                languages=[
                    'py3',
                ]
            )
            # convert() does not return Rule objects anynore, peek into the build env
            # to see what rules have been generated
            for rule in self._state.parser._build_env_stack[-1].rules:
                rule = rule.rule
                if rule.attributes['name'] == "name-cpp2":
                    self.assertEqual('cxx_library', rule.type)
                    break
            else:
                self.fail('cpp2 thrift language not added for py3 lang target')

    def test_cpp2_options_copy_to_py3_options(self):
        OPTIONS = str("BLAHBLAHBLAH")
        with self._state.parser._with_stacked_build_env(BuildFileContext("base")):
            self._converter.convert(
                'base',
                'name',
                thrift_srcs={'service.thrift': []},
                languages=['py3', 'cpp2'],
                thrift_cpp2_options=OPTIONS,
            )
            # convert() does not return Rule objects anynore, peek into the build env
            # to see what rules have been generated
            for rule in self._state.parser._build_env_stack[-1].rules:
                rule = rule.rule
                if rule.attributes['name'] == "name-py3-service.thrift":
                    self.assertEqual('genrule', rule.type)
                    self.assertTrue(OPTIONS in rule.attributes['cmd'])
                    break
            else:
                self.fail('failed to find py3 thrift compiler target')
