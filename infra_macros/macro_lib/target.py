#!/usr/bin/env python

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

# TODO(T20914511): Until the macro lib has been completely ported to
# `include_defs()`, we need to support being loaded via both `import` and
# `include_defs()`.  These ugly preamble is thus here to consistently provide
# `allow_unsafe_import()` regardless of how we're loaded.
import contextlib
try:
    allow_unsafe_import
except NameError:
    @contextlib.contextmanager
    def allow_unsafe_import(*args, **kwargs):
        yield

import collections
from typing import Optional, Tuple, Union  # noqa F401

with allow_unsafe_import():
    import sys


RuleTarget = (
    collections.namedtuple(
        'RuleTarget',
        [
            'repo',
            'base_path',
            'name',
        ],
    ))


def parse_target(
    target, default_repo=None, default_base_path=None
):  # type: (str, Optional[str], Optional[str]) -> RuleTarget
    """
    Convert the given build target into a RuleTarget
    """

    # Normalize the target by removing the leading `@/`.
    normalized = None
    if target.startswith('@/'):
        normalized = target[2:]
    elif target.startswith(':'):
        normalized = target
    else:
        raise ValueError(
            'rule name must start with "@/" (when absolute) or ":" '
            '(when relative): "{}"'
            .format(target))

    # Split the target into its various parts.
    parts = normalized.split(':')
    if len(parts) < 2:
        raise ValueError(
            'rule name must contain at least one \':\' character: "{}"'
            .format(target))
    elif len(parts) == 2:
        repo = default_repo
        # Remove forward slashes.
        base = parts[0].rstrip('/') if parts[0] else default_base_path
        name = parts[1]

    elif len(parts) == 3:
        repo = parts[0]
        base = parts[1].rstrip('/')
        name = parts[2]

    else:
        raise ValueError(
            'rule name has too many \':\' characters (more than 3): '
            '"{}"'
            .format(target))

    return RuleTarget(repo, base, name)


def parse_external_dep(
    raw_target, lang_suffix='', default_repo=None
):  # type: (Union[str, Tuple[str], Tuple[str, str], Tuple[str, str, str], Tuple[str, str, str, str]], str, Optional[str]) -> Tuple[RuleTarget, str]
    """
    Normalize the various ways users can specify an external dep into a
    (RuleTarget, version) tuple.
    """

    if isinstance(raw_target, tuple):
        target = raw_target
    elif isinstance(
        raw_target,
        str if sys.version_info[0] >= 3 else basestring  # noqa F821
    ):
        target = (raw_target, )
    else:
        raise TypeError(
            'external dependency should be tuple or string, not int')

    if len(target) in (1, 2):
        repo = default_repo
        base = target[0]
        if len(target) == 2:
            version = target[1]
        else:
            version = None
        name = target[0] + lang_suffix

    elif len(target) == 3:
        repo = default_repo
        base = target[0]
        version = target[1]
        name = target[2]

    elif len(target) == 4:
        repo = target[0]
        base = target[1]
        version = target[2]
        name = target[3]

    else:
        raise ValueError(
            'illegal external dependency {!r}: must have 1, 2, 3, or 4 '
            'elements'
            .format(raw_target))

    return RuleTarget(repo, base, name), version
