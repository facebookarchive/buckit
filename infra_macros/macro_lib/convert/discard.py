#!/usr/bin/env python2

# Copyright 2015- Facebook Inc.  All Rights Reserved.

# Converter that discards the rules passed to it.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")


class DiscardingConverter(base.Converter):

    def __init__(self, context, rule_type):
        super(DiscardingConverter, self).__init__(context)
        self._rule_type = rule_type

    def convert(self, *args, **kwargs):
        return []

    def get_fbconfig_rule_type(self):
        return self._rule_type
