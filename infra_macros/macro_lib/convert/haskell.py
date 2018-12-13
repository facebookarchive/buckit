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

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:build_mode.bzl", _build_mode="build_mode")
load("@fbcode_macros//build_defs:custom_rule.bzl", "get_project_root_from_gen_dir")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs/lib:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:haskell_common.bzl", "haskell_common")
load("@fbcode_macros//build_defs/lib:haskell_rules.bzl", "haskell_rules")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:haskell_haddock.bzl", "haskell_haddock")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")


class HaskellConverter(base.Converter):

    def __init__(self, context, rule_type, buck_rule_type=None):
        super(HaskellConverter, self).__init__(context)
        self._rule_type = rule_type
        self._buck_rule_type = buck_rule_type or rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def is_binary(self):
        return self.get_fbconfig_rule_type() in (
            'haskell_binary',
            'haskell_unittest')

    def is_deployable(self):
        return self.get_fbconfig_rule_type() in (
            'haskell_binary',
            'haskell_unittest',
            'haskell_ghci')

    def is_test(self):
        return self.get_fbconfig_rule_type() in ('haskell_unittest',)

    def convert_rule(
            self,
            base_path,
            name=None,
            main=None,
            srcs=(),
            deps=(),
            external_deps=(),
            packages=(),
            compiler_flags=(),
            warnings_flags=(),
            lang_opts=(),
            enable_haddock=False,
            haddock_flags=None,
            enable_profiling=None,
            ghci_bin_dep=None,
            ghci_init=None,
            extra_script_templates=(),
            eventlog=None,
            link_whole=None,
            force_static=None,
            fb_haskell=True,
            allocator='jemalloc',
            dlls={},
            visibility=None):

        return [
            Rule(self.get_buck_rule_type(), haskell_rules.convert_rule(
                rule_type=self.get_fbconfig_rule_type(),
                base_path=base_path,
                name=name,
                main=main,
                srcs=srcs,
                deps=deps,
                external_deps=external_deps,
                packages=packages,
                compiler_flags=compiler_flags,
                warnings_flags=warnings_flags,
                lang_opts=lang_opts,
                enable_haddock=enable_haddock,
                haddock_flags=haddock_flags,
                enable_profiling=enable_profiling,
                ghci_bin_dep=ghci_bin_dep,
                ghci_init=ghci_init,
                extra_script_templates=extra_script_templates,
                eventlog=eventlog,
                link_whole=link_whole,
                force_static=force_static,
                fb_haskell=fb_haskell,
                allocator=allocator,
                dlls=dlls,
                visibility=visibility
            ))
        ]

    def convert_unittest(
            self,
            base_path,
            name,
            tags=(),
            env=None,
            visibility=None,
            **kwargs):
        """
        Buckify a unittest rule.
        """

        rules = []

        # Generate the test binary rule and fixup the name.
        binary_name = name + '-binary'
        binary_rules = (
            self.convert_rule(
                base_path,
                name=binary_name,
                visibility=visibility,
                **kwargs))
        rules.extend(binary_rules)

        platform = platform_utils.get_platform_for_base_path(base_path)

        # Create a `sh_test` rule to wrap the test binary and set it's tags so
        # that testpilot knows it's a haskell test.
        fb_native.sh_test(
            name=name,
            visibility=get_visibility(visibility, name),
            test=':' + binary_name,
            env=env,
            labels=(
                label_utils.convert_labels(platform, 'haskell', 'custom-type-hs', *tags)),
        )

        return rules

    def convert_library(self, base_path, name, dll=None, **kwargs):
        """
        Generate rules for a haskell library.
        """

        if dll is None:
            return self.convert_rule(base_path, name, **kwargs)
        else:
            haskell_rules.dll(base_path, name, dll, **kwargs)
            return []

    def convert(self, base_path, *args, **kwargs):
        """
        Generate rules for a haskell rule.
        """

        rtype = self.get_fbconfig_rule_type()
        if rtype == 'haskell_binary':
            return self.convert_rule(base_path, *args, **kwargs)
        if rtype == 'haskell_library':
            return self.convert_library(base_path, *args, **kwargs)
        elif rtype == 'haskell_unittest':
            return self.convert_unittest(base_path, *args, **kwargs)
        elif rtype == 'haskell_ghci':
            return self.convert_rule(base_path, *args, **kwargs)
        elif rtype == 'haskell_haddock':
            haskell_haddock(*args, **kwargs)
            return []
        else:
            raise Exception('unexpected type: ' + rtype)
