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


__all__ = ['Rule']


class Rule(collections.namedtuple('Rule', ['type', 'attributes'])):
    __slots__ = ()

    @property
    def target_name(self):
        """Get the relative target name for the rule"""
        return ':{}'.format(self.attributes['name'])
