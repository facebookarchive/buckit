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

with allow_unsafe_import():
    import os

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))


class JsConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(JsConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_node_module_name(self, name, node_module_name=None):
        return name if node_module_name is None else node_module_name

    def convert_deps(self, base_path, deps, external_deps):
        """
        """

        out_deps = []

        for dep in deps:
            out_deps.append(
                self.convert_build_target(
                    base_path,
                    dep,
                    platform=self.get_platform()))

        for dep in external_deps:
            out_deps.append(
                self.convert_external_build_target(
                    dep,
                    platform=self.get_platform()))

        return out_deps

    def get_platform(self):
        """
        Node rules always use the platforms set in the root PLATFORM file.
        """

        return super(JsConverter, self).get_platform('')

    def get_node_path(self, version_string):
        path_template = '/usr/local/fbcode/{}/bin/node-{}'

        platform = self.get_platform()
        config = self.get_third_party_config(platform)
        fallback_path = path_template.format(
            platform,
            config['build']['projects']['node'],
        )

        if (version_string):
            path = path_template.format(
                platform,
                version_string,
            )
            if (os.path.isfile(path)):
                return path
            print('Cannot find "{}". Falling back to "{}".'.format(
                path,
                fallback_path
            ))
        return fallback_path

    def generate_modules_tree(
            self,
            base_path,
            name,
            srcs,
            deps,
            visibility):
        """
        Generate a rule which exports the transitive set of node modules.
        """

        cmds = []

        for dep in deps:
            cmds.append('rsync -a $(location {})/ "$OUT"'.format(dep))

        # Copy files from sources and make their dirs.
        files = collections.OrderedDict()
        dirs = collections.OrderedDict()
        for dst, raw_src in srcs.items():
            src = self.get_source_name(raw_src)
            dst = os.path.join('"$OUT"', dst)
            dirs[os.path.dirname(dst)] = None
            files[dst] = src
        cmds.append('mkdir -p ' + ' '.join(dirs))
        for dst, src in files.items():
            cmds.append('cp {} {}'.format(src, dst))

        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = os.curdir
        attrs['srcs'] = srcs.values()
        attrs['cmd'] = ' && '.join(cmds)
        return Rule('genrule', attrs)

    def convert_node_module_external(
            self,
            base_path,
            name,
            node=None,
            node_module_name=None,
            deps=(),
            external_deps=(),
            visibility=None):

        rules = []

        # External node modules package their entire project directory.
        root = (
            os.path.join(
                'node_modules',
                self.get_node_module_name(name, node_module_name)))
        out_srcs = collections.OrderedDict()
        for src in self._context.buck_ops.glob(['**/*']):
            out_srcs[os.path.join(root, src)] = src

        rules.append(
            self.generate_modules_tree(
                base_path,
                name,
                out_srcs,
                self.convert_deps(base_path, deps, external_deps),
                visibility))

        return rules

    def convert_npm_module(
            self,
            base_path,
            name,
            srcs,
            node=None,
            node_module_name=None,
            deps=(),
            external_deps=(),
            visibility=None):

        rules = []

        # NPM modules package their listed sources.
        root = (
            os.path.join(
                'node_modules',
                self.get_node_module_name(name, node_module_name)))
        out_srcs = collections.OrderedDict()
        for src in sorted(srcs):
            src_name = self.get_source_name(src)
            out_srcs[os.path.join(root, src_name)] = src

        rules.append(
            self.generate_modules_tree(
                base_path,
                name,
                out_srcs,
                self.convert_deps(base_path, deps, external_deps),
                visibility))

        return rules

    def convert_executable(
            self,
            base_path,
            name,
            index,
            node=None,
            node_flags=(),
            srcs=(),
            deps=(),
            external_deps=(),
            visibility=None):

        rules = []

        # Setup the modules tree formed by this rule's sources and the sources
        # of it's transitive deps.
        modules_tree = (
            self.generate_modules_tree(
                base_path,
                name + '-modules',
                collections.OrderedDict(
                    [(os.path.join(base_path, s), s) for s in srcs]),
                self.convert_deps(base_path, deps, external_deps),
                visibility))
        rules.append(modules_tree)

        # Use a genrule to call the JSAR builder, giving it the modules tree
        # and outputting and executable.
        attrs = collections.OrderedDict()
        attrs['name'] = name
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = name + '.jsar'
        attrs['executable'] = True
        attrs['cmd'] = ' '.join([
            '$(exe //tools/make_par:buck_make_jsar)',
            '--node=' + self.get_node_path(node),
            '--platform=' + self.get_platform(),
            '"$OUT"',
            os.path.join(base_path, index),
            '$(location :{})'.format(modules_tree.attributes['name']),
        ])
        rules.append(Rule('genrule', attrs))

        return rules

    def convert(self, base_path, name, visibility=None, **kwargs):
        """
        """

        rules = []

        rtype = self.get_fbconfig_rule_type()
        if rtype == 'js_executable':
            rules.extend(self.convert_executable(base_path, name, visibility=visibility, **kwargs))
        elif rtype == 'js_node_module_external':
            rules.extend(
                self.convert_node_module_external(base_path, name, visibility=visibility, **kwargs))
        elif rtype == 'js_npm_module':
            rules.extend(self.convert_npm_module(base_path, name, visibility=visibility, **kwargs))
        else:
            raise Exception('invalid rule type: ' + rtype)

        return rules
