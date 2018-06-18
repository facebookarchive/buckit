#!/usr/bin/env python2

# Copyright 2017-present Facebook. All Rights Reserved

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import collections
import os

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))


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
            'visibility',
            'executable',
        ])

    def get_download_rule(
            self,
            name,
            project,
            commit,
            artifact,
            path,
            visibility,
            executable
    ):
        attributes = collections.OrderedDict()
        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility
        attributes['out'] = os.path.basename(path)
        attributes['srcs'] = []
        bash = """
            # TODO(T25517543): The filesystem interface to dewey is deprecated,
            # but used here anyway :( as a workaround for a dewey cli issue.
            deprecated_file=/mnt/dewey/{project}/.commits/{commit}/{tag}/{path}
            if [[ -f $deprecated_file ]] ; then
              cat "$deprecated_file" > $OUT
            else
              dewey cat --project {project} --commit {commit} --tag {tag} \
                        --path {path} --dest $OUT
            fi
            {make_executable}
        """.format(
            project=project,
            commit=commit,
            tag=artifact,
            path=path,
            make_executable="chmod +x $OUT" if executable else ""
        )
        attributes['bash'] = bash
        attributes['executable'] = executable
        return Rule('genrule', attributes)

    def convert(
            self,
            base_path,
            name,
            project,
            commit,
            artifact,
            path,
            visibility=None,
            executable=False,
            **kwargs
    ):
        rules = []
        rules.append(self.get_download_rule(name, project, commit, artifact, path, visibility, executable))
        return rules
