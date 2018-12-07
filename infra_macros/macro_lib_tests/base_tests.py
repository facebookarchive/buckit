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

import collections

from . import utils


class BaseConverterTest(utils.ConverterTestCase):

    def setUp(self):
        super(BaseConverterTest, self).setUp()
        try:
            self.setup_with_config({}, set())
        except:
            super(BaseConverterTest, self).tearDown()
            raise

    def setup_with_config(self, additional_configs, removed_configs):
        self._state = self._create_converter_state(
            additional_configs,
            removed_configs)
        self._base = (
            self._state.parser.load_include(
                'tools/build/buck/infra_macros/macro_lib/convert/base.py'))
        self._converter = self._base.Converter(self._state.context)

    def test_is_tp2(self):
        self.assertFalse(self._converter.is_tp2('hello/world'))
        self.assertTrue(self._converter.is_tp2('third-party-buck/foo'))

    def test_get_tp2_build_dat(self):
        base_path = 'base/path'
        build_dat = {
            'builds': {
                'build0': {
                    'foo': '1.0',
                }
            },
            'dependencies': {},
            'platform': 'platform007',
        }
        self.write_build_dat(base_path, build_dat)
        actual_build_dat = self._converter.get_tp2_build_dat(base_path)
        self.assertEqual(actual_build_dat, build_dat)

    def test_get_tp2_project_builds_with_single_build(self):
        base_path = 'base/path'
        build_dat = {
            'builds': {
                'build0': {
                    'foo': '1.0',
                }
            },
            'dependencies': {},
            'platform': 'platform007',
        }
        self.write_build_dat(base_path, build_dat)
        actual_builds = self._converter.get_tp2_project_builds(base_path)
        expected_builds = collections.OrderedDict([(
            'build0', self._base.Tp2ProjectBuild(
                project_deps={
                    self._converter.get_dep_target(
                        self._converter.get_tp2_project_target('foo'),
                        platform=build_dat['platform']): '1.0',
                },
                subdir='',
                versions={'foo': '1.0'},
            ),
        )])
        self.assertEqual(actual_builds, expected_builds)

    def test_get_tp2_project_builds_with_multiple_builds(self):
        base_path = 'base/path'
        build_dat = {
            'builds': {
                'build0': {
                    'foo': '1.0',
                },
                'build1': {
                    'foo': '2.0',
                }
            },
            'dependencies': {},
            'platform': 'platform007',
        }
        self.write_build_dat(base_path, build_dat)
        actual_builds = self._converter.get_tp2_project_builds(base_path)
        expected_builds = collections.OrderedDict([
            ('build0', self._base.Tp2ProjectBuild(
                project_deps={
                    self._converter.get_dep_target(
                        self._converter.get_tp2_project_target('foo'),
                        platform=build_dat['platform']): '1.0',
                },
                subdir='build0',
                versions={'foo': '1.0'},
            ),),
            ('build1', self._base.Tp2ProjectBuild(
                project_deps={
                    self._converter.get_dep_target(
                        self._converter.get_tp2_project_target('foo'),
                        platform=build_dat['platform']): '2.0',
                },
                subdir='build1',
                versions={'foo': '2.0'},
            ),),
        ])
        self.assertEqual(actual_builds, expected_builds)

    def test_normalize_external_dep(self):
        self.assertEquals(
            self._converter.normalize_external_dep('single'),
            self._base.RuleTarget('single', 'single', 'single'))
        self.assertEquals(
            self._converter.normalize_external_dep(
                'single',
                lang_suffix='-py'),
            self._base.RuleTarget('single', 'single', 'single-py'))
        self.assertEquals(
            self._converter.normalize_external_dep(('project', None)),
            self._base.RuleTarget('project', 'project', 'project'))
        self.assertEquals(
            self._converter.normalize_external_dep(
                ('third-party', 'project', None, 'name')),
            self._base.RuleTarget('third-party', 'project', 'name'))
        with self.assertRaises(TypeError):
            self._converter.normalize_external_dep(13)
        with self.assertRaises(ValueError):
            self._converter.normalize_external_dep(
                ('way', 'way', 'too', 'many', 'parts'))
