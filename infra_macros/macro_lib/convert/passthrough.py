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

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
include_defs("{}/rule.py".format(macro_root))
include_defs("{}/fbcode_target.py".format(macro_root), "target")


class PassthroughConverter(base.Converter):
    """
    Passthrough rules as-is.
    """

    def __init__(
            self,
            context,
            fbconfig_rule_type,
            buck_rule_type,
            default_attrs=None,
            whitelist=None,
            whitelist_error_msg=None,
            convert_targets_on=None):
        super(PassthroughConverter, self).__init__(context)
        self._fbconfig_rule_type = fbconfig_rule_type
        self._buck_rule_type = buck_rule_type
        self._default_attrs = default_attrs or {}
        self._whitelist = whitelist
        self._whitelist_error_msg = whitelist_error_msg
        self._convert_targets_on = convert_targets_on

    def get_fbconfig_rule_type(self):
        return self._fbconfig_rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def convert(self, base_path, **kwargs):

        # First check the whitelist.
        if (self._context.config.forbid_raw_buck_rules and
                self._whitelist is not None and
                (base_path, kwargs.get('name')) not in self._whitelist):
            msg = self._whitelist_error_msg
            if msg is None:
                msg = 'rule is not whitelisted'
            raise ValueError(
                '{}(): {}'.format(self.get_fbconfig_rule_type(), msg))

        if self._convert_targets_on:
            for key in self._convert_targets_on:
                val = kwargs.get(key)
                if isinstance(val, basestring):
                    val = self.get_dep_target(target.parse_target(val, base_path))
                    kwargs[key] = val
                elif isinstance(val, list):
                    val = [
                        self.get_dep_target(target.parse_target(tgt, base_path))
                        for tgt in val
                    ]
                    kwargs[key] = val


        attributes = collections.OrderedDict()
        attributes.update(self._default_attrs)
        attributes.update(kwargs)
        return [Rule(self.get_buck_rule_type(), attributes)]
