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

import os
import shlex
import pipes
import platform
import collections

from . import base
from ..rule import Rule


# An "alias" for a bash command to get a relative path.  This is pretty
# gross, but I don't know another way to relative paths.
RELPATH = ' '.join([
    'python',
    '-c',
    '"import sys, os; '
    'sys.stdout.write(os.path.relpath(sys.argv[1], sys.argv[2]))"',
])


class CustomRuleConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'custom_rule'

    def get_buck_rule_type(self):
        return 'genrule'

    def get_output_dir(self, name):
        return name + '-outputs'

    def convert_main_rule(
            self,
            base_path,
            name,
            deployable=None,
            build_script=None,
            build_script_path=None,
            build_script_dep=None,
            build_args=None,
            external_deps=[],
            output_gen_files=[],
            output_bin_files=[],
            tools=(),
            print_output=None,
            print_stdout=None,
            print_stderr=None,
            srcs=[],
            deps=[],
            strict=True,
            output_subdir=None,
            env=None):

        if strict and build_script_path is not None:
            raise ValueError(
                '`build_script_path` is not supported in `strict` mode')

        out = self.get_output_dir(name)
        platform = self.get_platform(base_path)
        extra_rules = []

        attributes = collections.OrderedDict()

        attributes['name'] = out
        attributes['out'] = out

        if srcs:
            attributes['srcs'] = self.convert_source_list(base_path, srcs)

        fbcode_dir = (
            os.path.join('$GEN_DIR', self.get_fbcode_dir_from_gen_dir()))
        install_dir = '$OUT'

        # Build up a custom path using any extra tools specified by the
        # `custom_rule`.
        path = []
        tool_bin_rules = []
        for tool in sorted(tools):
            tool_path = self.get_tp2_tool_path(tool, platform)
            tool_bin_rules.append(
                '//{}/tools:{}/bin'
                .format(self.get_third_party_root(platform), tool))

            # It's possible that the tool that the user wants hasn't been
            # added to buck's tp2 setup.  In this case, throw a hard error
            # rather than allowing it to get silently ignored in our path.
            if not os.path.exists(tool_path):
                raise Exception(
                    'Canot find tool `{}` at path `{}`.  You may need to '
                    'add this project to the "tools" section of '
                    '`third-party-buck/config.json` and update the symlinks '
                    '(https://fburl.com/121631220)'
                    .format(tool, tool_path))

            # Add the projects `bin` dir to the path.
            path.append(os.path.join(fbcode_dir, tool_path, 'bin'))

        # Make sure the original path is still available.
        path.append('$PATH')

        # Initially, create the output directory.
        cmd = 'mkdir -p $OUT && '

        # Assemble and pass in the environment overrides.
        env = collections.OrderedDict(sorted(env.items()) if env else [])
        if not strict:
            env['FBCODE_DIR'] = fbcode_dir
        env['INSTALL_DIR'] = install_dir
        env['PATH'] = os.pathsep.join(path)
        env['FBCODE_BUILD_MODE'] = self._context.mode
        env['FBCODE_BUILD_TOOL'] = 'buck'
        env['FBCODE_PLATFORM'] = platform
        # Add in the tool rules to the environment.  They won't be consumed by
        # the script/user, but they will affect the rule key.
        env['FBCODE_THIRD_PARTY_TOOLS'] = (
            ':'.join(
                '$(location {})'.format(r) for r in sorted(tool_bin_rules)))
        cmd += (
            'env ' +
            ' '.join(['{}={}'.format(k, v) for k, v in env.iteritems()]) +
            ' ')

        # If a raw build script path was specified, add that to the command.
        if build_script is not None:
            full_path = (
                os.path.normpath(
                    os.path.join(
                        build_script_path or base_path,
                        build_script)))

            # If `build_script` resolves to a absolute path, error out, since
            # Buck doesn't currently have a way to make these affect the rule
            # key.
            if os.path.isabs(full_path):
                raise ValueError(
                    'absolute build script paths are not supported: {}'
                    .format(full_path))

            # Wrap the build script in an `export_file` rule and reference it
            # in the command via a location macro so that it gets properly
            # represented in the rule key.
            attrs = collections.OrderedDict()
            attrs['name'] = out + '-build-script'
            attrs['out'] = os.path.join(out + '-build-script', full_path)
            attrs['src'] = os.path.relpath(full_path, base_path)
            extra_rules.append(Rule('export_file', attrs))
            cmd += '$(location :{}-build-script)'.format(out)

        # Otherwise, if just `build_script_dep`, convert this straight to a
        # executable macro.
        else:
            cmd += '$(exe {})'.format(
                self.convert_build_target(base_path, build_script_dep))

        # Add the fbconfig-specified args that point to special directories.
        if not strict:
            cmd += ' --fbcode_dir=' + fbcode_dir
        cmd += ' --install_dir=' + install_dir

        bin_refs = 0

        # Add in additional build args.
        if build_args:

            # If we see the fbmake output dir references in build args we need
            # to do special processing to plug this up the the actual deps that
            # generate the outputs.
            if '$(FBMAKE_BIN_ROOT)' in build_args:
                for arg in shlex.split(build_args):
                    cmd += ' '
                    # If we see a reference to the build output dir, we need to
                    # convert this to a `location` macro.  This is hard since we
                    # don't know the final output paths of our deps.  So, we use
                    # a heuristic that the leading deps of this `custom_rule`
                    # correspond to the args in the command.
                    if arg.startswith('$(FBMAKE_BIN_ROOT)'):
                        dep = (
                            self.convert_build_target(
                                base_path,
                                deps[bin_refs]))
                        cmd += (
                            '`{0} $(location {1}) {2}`'
                            .format(RELPATH, dep, fbcode_dir))
                        bin_refs += 1
                    else:
                        cmd += pipes.quote(arg)

            # Otherwise, just pass the build args directly.
            else:
                cmd += ' ' + self.convert_blob_with_macros(base_path, build_args, platform=platform)

        if bin_refs < len(deps):
            # Some dependencies were not converted into $(location) macros. Buck
            # does not support dependencies for genrules since it is more
            # efficient if it can track exactly which outputs are used, but as
            # long as rules do not rely on the side effects of their
            # dependencies and find their output properly, adding an ignored
            # $(location) macro should be almost equivalent to a dep.
            cmd += ' #'
            while bin_refs < len(deps):
                dep = self.convert_build_target(base_path, deps[bin_refs])
                cmd += ' $(location {0})'.format(dep)
                bin_refs += 1

        attributes['cmd'] = cmd

        return [Rule(self.get_buck_rule_type(), attributes)] + extra_rules

    def convert_output_rule(
            self,
            base_path,
            name,
            out_name,
            out):

        attributes = collections.OrderedDict()
        attributes['name'] = out_name
        attributes['out'] = out
        cmds = {
            'Linux': ('mkdir -p `dirname $OUT` && '
                      'ln -T $(location :{output_dir})/{out} $OUT'),
            'Darwin': ('mkdir -p `dirname $OUT` && '
                       'ln $(location :{output_dir})/{out} $OUT'),
        }

        attributes['cmd'] = cmds.get(platform.system(), cmds['Linux']).format(
            output_dir=self.get_output_dir(name),
            out=out)

        return [Rule(self.get_buck_rule_type(), attributes)]

    def convert(
            self,
            base_path,
            name=None,
            output_gen_files=[],
            output_bin_files=[],
            **kwargs):

        rules = []

        # Ensure that we let people know if they misused the lib
        if not isinstance(output_gen_files, (list, tuple)):
            raise ValueError(
                'custom_rule(): {}:{}: output_gen_files must be a list of '
                'filenames, got {!r}'.format(base_path, name, output_gen_files))

        outs = []
        outs.extend(output_gen_files)
        outs.extend(output_bin_files)

        # Make sure output params don't escape install directory.
        for out in outs:
            if os.pardir in out.split(os.sep):
                raise ValueError(
                    'custom_rule(): output filename cannot contain '
                    '`..`: {!r}'
                    .format(out))

        # Add the main rule which runs the custom rule and stores its outputs
        # in a ZIP archive.
        rules.extend(self.convert_main_rule(base_path, name, **kwargs))

        # For each output, create a `=<out>` rule which pulls it from the main
        # output directory so that consuming rules can use use one of the
        # multiple outs.
        for out in outs:
            out_name = '{0}={1}'.format(name, out)
            rules.extend(
                self.convert_output_rule(
                    base_path,
                    name,
                    out_name,
                    out))

        # When we just have a single output, also add a rule with the original
        # name which just unpacks the only listed output.  This allows consuming
        # rules to avoid the `=<out>` suffix.
        if len(outs) == 1:
            rules.extend(
                self.convert_output_rule(base_path, name, name, outs[0]))

        # Otherwise, use a dummy empty Python library to force runtime
        # dependencies to propagate onto all of the outputs of the custom rule.
        else:
            attrs = collections.OrderedDict()
            attrs['name'] = name
            attrs['deps'] = [':{0}={1}'.format(name, o) for o in outs]
            rules.append(Rule('python_library', attrs))

        return rules
