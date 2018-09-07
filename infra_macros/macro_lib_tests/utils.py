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
import contextlib
import json
import os
import platform
import shutil
import sys
import tempfile
import unittest

from tools.build.buck.parser import Parser

from ..macro_lib import BuildMode


ConverterState = (
    collections.namedtuple(
        'ConverterState',
        ['context', 'parser', 'build_file_deps', 'include_defs']))


class ConverterTestCase(unittest.TestCase):

    def setUp(self):
        # TODO(T20914511): Some macro lib components still use `import`.  Remove once
        # this is fixed.
        sys.path.insert(0, os.path.join(os.getcwd(), 'tools/build/buck/infra_macros'))

        self._root = tempfile.mkdtemp()
        self._old_cwd = os.getcwd()
        os.chdir(self._root)

    def tearDown(self):
        shutil.rmtree(self._root, True)
        os.chdir(self._old_cwd)
        del sys.path[0]

    def mkdir(self, dirpath):
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)

    def write_file(self, path, contents=''):
        self.mkdir(os.path.dirname(path))
        with open(path, 'w') as f:
            f.write(contents)

    def write_build_dat(self, base_path, build_dat):
        self.write_file(
            os.path.join(base_path, 'build.dat'),
            json.dumps(build_dat))

    def _create_converter_state(self, extra_configs=None, removed_configs=None):
        configs = {
            ('repositories', 'bazel_skylib'): '../xplat/third-party/bazel-skylib',
            ('repositories', 'fbcode_macros'): 'tools/build/buck/infra_macros/fbcode_macros',
            ('repositories', 'fbcode'): '.',
            ('repositories', 'fbsource'): '..',
            ('repositories', 'xplat'): '../xplat',
            ('fbcode', 'platform'): 'platform007',
            ('fbcode', 'macro_lib'): '//tools/build/buck/infra_macros/macro_lib',
            ('fbcode', 'third_party_buck_directory'): 'third-party-buck',
            ('fbcode', 'third_party_config_path'): 'third-party-buck/config.py',
            ('fbcode', 'add_auto_headers_glob'): 'true',
            ('fbcode', 'fbcode_style_deps_are_third_party'): 'false',
            ('fbcode', 'unknown_cells_are_third_party'): 'true',
            ('fbcode', 'third_party_use_build_subdir'): 'true',
            ('fbcode', 'third_party_use_platform_subdir'): 'true',
            ('fbcode', 'third_party_use_tools_subdir'): 'true',
            ('fbcode', 'core_tools_include_path'): '//tools/build/buck/config.py',
            ('fbcode', 'use_build_info_linker_flags'): 'true',
            ('fbcode', 'require_platform'): 'true',
            ('fbcode', 'allocators.jemalloc'): '//common/memory:jemalloc',
            ('fbcode', 'allocators.jemalloc_debug'): '//common/memory:jemalloc_debug',
            ('fbcode', 'allocators.tcmalloc'): '//common/memory:tcmalloc',
            ('fbcode', 'allocators.malloc'): '',
            ('fbcode', 'fbcode_style_deps'): 'true',
            ('fbcode', 'auto_pch_blacklist'): 'exclude/,exclude2/subdir/',
        }
        if extra_configs:
            configs.update(extra_configs)
        if removed_configs:
            for config in removed_configs:
                del configs[config]

        # Setup the parser.
        tiered_config = collections.defaultdict(dict)
        for (section, field), value in configs.items():
            tiered_config[section][field] = value
        parser = Parser.create_from_config(tiered_config, root=self._old_cwd)

        def read_config_func(s, f, d=None):
            return configs.get((s, f), d)

        @contextlib.contextmanager
        def import_func():
            yield

        config = parser.load_include('tools/build/buck/infra_macros/fbcode_macros/build_defs/config.bzl')
        create_build_mode = parser.load_include('tools/build/buck/infra_macros/fbcode_macros/build_defs/create_build_mode.bzl')
        base = parser.load_include('tools/build/buck/infra_macros/macro_lib/convert/base.py')

        parsed_config = config.config

        build_file_deps = []
        include_defs = []
        buck_ops = (
            base.BuckOperations(
                add_build_file_dep=lambda dep: build_file_deps.append(dep),
                glob=lambda *a, **kw: [],
                include_defs=lambda dep: include_defs.append(dep),
                read_config=read_config_func))
        context = (
            base.Context(
                buck_ops=buck_ops,
                build_mode=create_build_mode.create_build_mode(),
                default_compiler='gcc',
                global_compiler=None,
                coverage=False,
                link_style='shared',
                mode='opt',
                sanitizer=None,
                lto_type=None,
                third_party_config={
                    'platforms': {
                        'platform007': {'architecture': platform.machine()},
                        'platform': {'architecture': platform.machine()},
                    },
                },
                config=parsed_config))
        return ConverterState(
            context=context,
            parser=parser,
            build_file_deps=build_file_deps,
            include_defs=include_defs)
