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

import re
import os
import collections

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")

def first(*args):
    for arg in args:
        if arg is not None:
            return arg
    return None


def is_collection(obj):
    """
    Return whether the object is a array-like collection.
    """

    for typ in (list, set, tuple):
        if isinstance(obj, typ):
            return True

    return False


class CppLibraryExternalCustomConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'cpp_library_external_custom'

    def get_buck_rule_type(self):
        return 'prebuilt_cxx_library_group'

    def translate_ref(self, lib, libs, shared=False):
        if shared:
            return 'lib{}.so'.format(lib)
        else:
            return str(libs.index(lib))

    def translate_link(self, args, libs, shared=False):
        """
        Translate the given link args into their buck equivalents.
        """

        out = []

        # Match name-only library references.
        lib_re = re.compile('^\\{LIB_(.*)\\}$')

        # Match full path library references.
        rel_lib_re = re.compile('^-l\\{lib_(.*)\\}$')

        # Iterate over args, translating them to their buck equivalents.
        i = 0
        while i < len(args):

            # Translate `{LIB_<name>}` references to buck-style macros.
            m = lib_re.search(args[i])
            if m is not None:
                out.append(
                    '$(lib {})'.format(
                        self.translate_ref(m.group(1), libs, shared)))
                i += 1
                continue

            # Translate `-L{dir} -l{lib_<name>}` references to buck-style
            # macros.
            if shared and args[i] == '-L{dir}' and i < len(args) - 1:
                m = rel_lib_re.match(args[i + 1])
                if m is not None:
                    out.append(
                        '$(rel-lib {})'.format(
                            self.translate_ref(m.group(1), libs, shared)))
                    i += 2
                    continue

            # Handle the "all libs" placeholder.
            if args[i] == '{LIBS}':
                for lib in libs:
                    out.append(
                        '$(lib {})'.format(
                            self.translate_ref(lib, libs, shared)))
                i += 1
                continue

            # Otherwise, pass the argument straight to the linker.
            out.append('-Xlinker')
            out.append(args[i])
            i += 1

        return out

    def convert(
            self,
            base_path,
            name,
            lib_dir='lib',
            include_dir=['include'],
            static_link=None,
            static_libs=None,
            static_pic_link=None,
            static_pic_libs=None,
            shared_link=None,
            shared_libs=None,
            propagated_pp_flags=(),
            external_deps=(),
            visibility=None):

        platform = self.get_tp2_platform(base_path)

        attributes = collections.OrderedDict()
        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility

        out_static_link = (
            None if static_link is None
            else self.translate_link(static_link, static_libs))
        out_static_libs = (
            None if static_libs is None
            else [os.path.join(lib_dir, 'lib{}.a'.format(s))
                  for s in static_libs])

        out_static_pic_link = (
            None if static_pic_link is None
            else self.translate_link(static_pic_link, static_pic_libs))
        out_static_pic_libs = (
            None if static_pic_libs is None
            else [os.path.join(lib_dir, 'lib{}.a'.format(s))
                  for s in static_pic_libs])

        out_shared_link = (
            None if shared_link is None
            else self.translate_link(shared_link, shared_libs, shared=True))
        out_shared_libs = (
            None if shared_libs is None
            else {'lib{}.so'.format(s):
                   os.path.join(lib_dir, 'lib{}.so'.format(s))
                       for s in shared_libs})

        attributes['static_link'] = first(out_static_link, out_static_pic_link)
        attributes['static_libs'] = first(out_static_libs, out_static_pic_libs)
        attributes['static_pic_link'] = (
            first(out_static_pic_link, out_static_link))
        attributes['static_pic_libs'] = (
            first(out_static_pic_libs, out_static_libs))
        attributes['shared_link'] = out_shared_link
        attributes['shared_libs'] = out_shared_libs

        out_include_dirs = []
        if is_collection(include_dir):
            out_include_dirs.extend(include_dir)
        else:
            out_include_dirs.append(include_dir)
        if out_include_dirs:
            attributes['include_dirs'] = out_include_dirs

        if propagated_pp_flags:
            attributes['exported_preprocessor_flags'] = propagated_pp_flags

        dependencies = []
        for target in external_deps:
            edep = src_and_dep_helpers.normalize_external_dep(target)
            dependencies.append(
                target_utils.target_to_label(edep, platform=platform))
        if dependencies:
            attributes['exported_deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)]
