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


class FbcodeTargetConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(FbcodeTargetConverterTest, self).setUp()
        try:
            self.setup_with_config({}, set())
        except:
            super(FbcodeTargetConverterTest, self).tearDown()

    def setup_with_config(self, additional_configs, removed_configs):
        self._state = self._create_converter_state(
            additional_configs,
            removed_configs)
        self._fbcode_target = (
            self._state.parser.load_include(
                'tools/build/buck/infra_macros/macro_lib/fbcode_target.py'))

    def test_parse_target(self):
        self.assertEquals(
            self._fbcode_target.parse_target(':target'),
            self._fbcode_target.RuleTarget(None, None, 'target'))
        self.assertEquals(
            self._fbcode_target.parse_target('@/fbcode:full:target'),
            self._fbcode_target.RuleTarget(None, 'full', 'target'))
        self.assertEquals(
            self._fbcode_target.parse_target('@/third-party:full:target'),
            self._fbcode_target.RuleTarget('third-party', 'full', 'target'))
        self.assertEquals(
            self._fbcode_target.parse_target('repo//full:target'),
            self._fbcode_target.RuleTarget('repo', 'full', 'target'))
        self.assertEquals(
            self._fbcode_target.parse_target('//full:target'),
            self._fbcode_target.RuleTarget(None, 'full', 'target'))
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('@/full:target')
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('@/repo:full:target'),
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('@invalid:target')
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('invalid:target')
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('@/invalid')
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('//invalid')
        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('repo:invalid:target')

    def test_parse_target_in_oss(self):
        self.setup_with_config({}, {('fbcode', 'fbcode_style_deps')})

        self.assertEquals(
            self._fbcode_target.parse_target(':target'),
            self._fbcode_target.RuleTarget(None, None, 'target'))
        self.assertEquals(
            self._fbcode_target.parse_target('//full:target'),
            self._fbcode_target.RuleTarget(None, 'full', 'target'))
        self.assertEquals(
            self._fbcode_target.parse_target('cell//full:target'),
            self._fbcode_target.RuleTarget('cell', 'full', 'target'))

        with self.assertRaises(ValueError):
            self._fbcode_target.parse_target('@/full:target')
