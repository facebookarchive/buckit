"""
A wrapper around `target.py`s parsing/formatting with fbcode-specific
customizations.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

include_defs('//tools/build/buck/infra_macros/macro_lib/config.py', 'config')
include_defs('//tools/build/buck/infra_macros/macro_lib/target.py', 'target')


__all__ = [
    'parse_target',
    'RootRuleTarget',
    'RuleTarget',
    'ThirdPartyRuleTarget',
]


# Re-export `target.RuleTarget` as this module hides that one.
RuleTarget = target.RuleTarget


def RootRuleTarget(base_path, name):
    return target.RuleTarget(None, base_path, name)


def ThirdPartyRuleTarget(project, rule_name):
    return target.RuleTarget(project, project, rule_name)


def parse_target(raw_target, base_path=None):
    """
    Convert the given build target into a RuleTarget
    """

    # A 'repo' is used as the cell name when generating a target except
    # when:
    #  - repo is None. This means that the rule is in the root cell
    #  - fbcode.unknown_cells_are_third_party is True. This will resolve
    #    unknown repositories as third-party libraries

    # This is the normal path for buck style dependencies. We do a little
    # parsing, but nothing too crazy. This allows OSS users to use the
    # FB macro library, but not have to use fbcode naming conventions
    if not config.fbcode_style_deps:
        if raw_target.startswith('@/'):
            raise ValueError(
                'rule name must not start with "@/" in repositories with '
                'fbcode style deps disabled')
        cell_and_target = raw_target.split('//', 2)
        path, rule = cell_and_target[-1].split(':')
        repo = None
        if len(cell_and_target) == 2 and cell_and_target[0]:
            repo = cell_and_target[0]
        path = path or base_path
        return target.RuleTarget(repo, path, rule)

    parsed = (
        target.parse_target(
            raw_target,
            default_base_path=base_path))

    # Normally in the monorepo, you can reference other directories
    # directly. When not in the monorepo, we need to map to a correct cell
    # for third-party use. A canonical example is folly. It is first-party
    # to Facebook, but third-party to OSS users, so we need to toggle what
    # '@/' means a little.
    # ***
    # We'll assume for now that all cells' names match their directory in
    # the monorepo.
    # ***
    # We can probably add more configuration later if necessary.
    if parsed.repo is None:
        if config.fbcode_style_deps_are_third_party:
            repo = parsed.base_path.split(os.sep)[0]
        else:
            repo = config.current_repo_name
        parsed = parsed._replace(repo=repo)

    # Some third party dependencies fall under rules like
    # know it's under the root cell
    if parsed.repo == config.current_repo_name:
        parsed = parsed._replace(repo=None)

    return parsed
