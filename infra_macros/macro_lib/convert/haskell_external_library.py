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
import os

from . import base
from ..rule import Rule


class HaskellExternalLibraryConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'haskell_external_library'

    def get_buck_rule_type(self):
        return 'haskell_prebuilt_library'

    def get_identifier_from_db(self, base_path, name, version):
        """
        Find the package identifier via inspecting the path to the package
        database.
        """

        package_conf_dir = os.path.join(base_path, 'lib/package.conf.d')
        if os.path.exists(package_conf_dir):
            for ent in os.listdir(package_conf_dir):
                if ent.startswith('{}-{}-'.format(name, version)):
                    return os.path.splitext(ent)[0]

        raise Exception(
            '//{}:{}: cannot lookup package identifier'
            .format(base_path, name))

    def convert(
            self,
            base_path,
            name=None,
            version=None,
            db=None,
            id=None,
            include_dirs=(),
            lib_dir=None,
            libs=(),
            linker_flags=(),
            external_deps=()):

        platform = self.get_tp2_build_dat(base_path)['platform']

        attributes = collections.OrderedDict()
        attributes['name'] = name

        out_exported_compiler_flags = []
        out_exported_compiler_flags.append('-expose-package')
        out_exported_compiler_flags.append('{}-{}'.format(name, version))
        attributes['exported_compiler_flags'] = out_exported_compiler_flags

        attributes['version'] = version
        attributes['db'] = db
        attributes['id'] = (
            id or self.get_identifier_from_db(base_path, name, version))

        out_linker_flags = []
        # There are some cyclical deps between core haskell libs which prevent
        # us from using `--as-needed`.
        if self._context.mode.startswith('dev'):
            out_linker_flags.append('-Wl,--no-as-needed')
        for flag in linker_flags:
            out_linker_flags.append('-Xlinker')
            out_linker_flags.append(flag)
        attributes['exported_linker_flags'] = out_linker_flags

        attributes['static_libs'] = (
            [os.path.join(lib_dir, 'lib{}.a'.format(l)) for l in libs])
        attributes['profiled_static_libs'] = (
            [os.path.join(lib_dir, 'lib{}_p.a'.format(l)) for l in libs])
        tp_config = self.get_third_party_config(platform)
        ghc_version = tp_config['tools']['projects']['ghc']
        shlibs = (
            [os.path.join(lib_dir, 'lib{}-ghc{}.so'.format(lib, ghc_version))
                for lib in libs])
        attributes['shared_libs'] = {os.path.basename(l): l for l in shlibs}

        # Forward C/C++ include dirs.
        attributes['cxx_header_dirs'] = include_dirs

        # If this is a tp2 project, verify that we just have a single inlined
        # build.  When this stops being true, we'll need to add versioned
        # subdir support for `prebuilt_haskell_library` rules (e.g. D4297963).
        if self.is_tp2(base_path):
            project_builds = self.get_tp2_project_builds(base_path)
            if (len(project_builds) != 1 or
                    project_builds.values()[0].subdir != ''):
                raise TypeError(
                    'haskell_external_library(): expected to find a single '
                    'inlined build for tp2 project "{}"'
                    .format(self.get_tp2_project_name(base_path)))

        dependencies = []

        # Add the implicit dep to our own project rule.
        project_dep = self.get_tp2_project_dep(base_path)
        if project_dep is not None:
            dependencies.append(project_dep)

        for target in external_deps:
            edep = self.normalize_external_dep(target)
            dependencies.append(
                self.get_dep_target(edep, source=target, platform=platform))

        if dependencies:
            attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
