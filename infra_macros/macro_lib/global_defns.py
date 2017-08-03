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


class AutoHeaders(object):
    """
    Enum with the various methods of automatically attaching headers to a C/C++
    rule.
    """

    NONE = 'none'

    # Uses a recursive glob to resolve all transitive headers under the given
    # directory.
    RECURSIVE_GLOB = 'recursive_glob'

    # Infer headers from sources of the rule.
    SOURCES = 'sources'
