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

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
load("@fbcode_macros//build_defs/lib:ocaml_common.bzl", "ocaml_common")


class OCamlConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(OCamlConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._rule_type

    def convert(
            self,
            base_path,
            name,
            srcs=(),
            deps=(),
            compiler_flags=None,
            ocamldep_flags=None,
            native=True,
            warnings_flags=None,
            supports_coverage=None,
            external_deps=(),
            visibility=None,
            ppx_flag=None,
            nodefaultlibs=False):

        attributes = ocaml_common.convert_ocaml(
            name=name,
            rule_type=self._rule_type,
            srcs=srcs,
            deps=deps,
            compiler_flags=compiler_flags,
            ocamldep_flags=ocamldep_flags,
            native=native,
            warnings_flags=warnings_flags,
            supports_coverage=supports_coverage,
            external_deps=external_deps,
            visibility=visibility,
            ppx_flag=ppx_flag,
            nodefaultlibs=nodefaultlibs,
        )

        return [Rule(self.get_buck_rule_type(), attributes)]
