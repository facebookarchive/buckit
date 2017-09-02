#!/usr/bin/env python2

# Copyright 2017-present Facebook. All Rights Reserved

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import collections
import os

from . import base
from ..rule import Rule


class DeweyArtifactConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'dewey_artifact'

    def get_buck_rule_type(self):
        return 'dewey_artifact'

    def get_allowed_args(self):
        return set([
            'name',
            'project',
            'commit',
            'artifact',
            'path',
            'deps',
            'visibility',
        ])

    def get_prebuilt_jar_rule(
            self,
            name,
            deps,
            visibility,
    ):
        attributes = collections.OrderedDict()
        attributes['name'] = name
        attributes['binary_jar'] = ':' + name + '_remote_file'
        attributes['deps'] = deps
        attributes['visibility'] = visibility
        return Rule('prebuilt_jar', attributes)

    def get_download_rule(
            self,
            name,
            project,
            commit,
            artifact,
            path,
    ):
        attributes = collections.OrderedDict()
        attributes['name'] = name + '_remote_file'
        attributes['out'] = os.path.basename(path)
        attributes['srcs'] = []
        bash = 'dewey cat --project %s --commit %s --tag %s --path %s --dest $OUT' % (
            project,
            commit,
            artifact,
            path,
        )
        attributes['bash'] = bash
        return Rule('genrule', attributes)

    def convert(
            self,
            base_path,
            name,
            project,
            commit,
            artifact,
            path,
            deps=[],
            visibility=[],
            **kwargs
    ):
        rules = []
        rules.append(self.get_prebuilt_jar_rule(name, deps, visibility))
        rules.append(self.get_download_rule(name, project, commit, artifact, path))
        return rules
