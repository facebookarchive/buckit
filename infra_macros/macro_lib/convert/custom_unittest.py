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
import pipes
import re

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))


class CustomUnittestConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'custom_unittest'

    def get_buck_rule_type(self):
        return 'sh_test'

    def is_generated_path(self, path):
        return path.startswith('$(FBMAKE_BIN_ROOT)') or path.startswith('_bin')

    def convert(
            self,
            base_path,
            name=None,
            command=None,
            emails=None,
            runtime_files=(),
            tags=(),
            type='json',
            deps=(),
            env=None,
            visibility=None):

        extra_rules = []
        platform = self.get_platform(base_path)

        attributes = collections.OrderedDict()

        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility
        attributes['type'] = type

        if command:
            bin_refs = 0

            # Convert any macros to their Buck-equivalents.
            command = (
                self.convert_args_with_macros(
                    base_path,
                    command,
                    platform=platform))

            # If the first parameter is a location macro, just extract the
            # build target and use that.
            m = re.search('^\$\((location|exe) (?P<test>.*)\)$', command[0])
            if m is not None:
                test = m.group('test')

            # If the first parameter appears to be generated, hook it up using
            # a dep source reference.
            elif self.is_generated_path(command[0]):
                test = self.convert_build_target(base_path, deps[bin_refs])
                bin_refs += 1

            # Otherwise, we need to plug it up using a `SourcePath`.  Since
            # these must be TARGETS-file relative, we generate a shadow rule
            # which builds a simple shell script that just invokes the first
            # arg, and use that to replace the first argument.
            else:
                # A simple shell script that just runs the first arg.
                script = os.linesep.join([
                    '#!/bin/sh',
                    'exec {0} "$@"'.format(pipes.quote(command[0])),
                ])
                command_attributes = collections.OrderedDict()
                command_attributes['name'] = name + '-command'
                if visibility is not None:
                    command_attributes['visibility'] = visibility
                command_attributes['out'] = name + '-command.sh'
                # The command just creates the above script with exec perms.
                command_attributes['cmd'] = (
                    'echo -e {0} > $OUT && chmod +x $OUT'
                    .format(pipes.quote(script)))
                test = ':{0}-command'.format(name)
                extra_rules.append(Rule('genrule', command_attributes))

            # If we see the fbmake output dir references in build args we need
            # to do special processing to plug this up the the actual deps that
            # generate the outputs.
            args = []
            for arg in command[1:]:
                # If we see a reference to the build output dir, we need to
                # convert this to a `location` macro.  This is hard since we
                # don't know the final output paths of our deps.  So, we use
                # a heuristic that the leading deps of this `custom_unittest`
                # correspond to the args in the command.
                if self.is_generated_path(arg):
                    dep = self.convert_build_target(base_path, deps[bin_refs])
                    args.append('$(location {0})'.format(dep))
                    bin_refs += 1
                else:
                    args.append(arg)

            # Set the `test` and `args` attributes.
            attributes['test'] = test
            if args:
                attributes['args'] = args

        # Construct the env, including the special build tool and build mode
        # variables.
        out_env = collections.OrderedDict()
        if env:
            out_env.update(
                sorted(
                    self.convert_env_with_macros(
                        base_path,
                        env,
                        platform=platform).items()))
        out_env['FBCODE_BUILD_TOOL'] = 'buck'
        out_env['FBCODE_BUILD_MODE'] = self._context.mode
        attributes['env'] = out_env

        # Translate runtime files into resources.
        if runtime_files:
            attributes['resources'] = runtime_files

        if self.is_test(self.get_buck_rule_type()):
            attributes['labels'] = (
                self.convert_labels(
                    platform,
                    'custom',
                    'custom-type-' + type,
                    *tags))

        dependencies = []
        for target in deps:
            dependencies.append(self.convert_build_target(base_path, target))
        if dependencies:
            attributes['deps'] = dependencies

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules
