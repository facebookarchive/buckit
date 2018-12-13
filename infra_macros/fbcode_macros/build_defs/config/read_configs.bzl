# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Simple helpers for reading configurations
"""

load("@fbcode_macros//build_defs/lib:shell.bzl", "shell")

def read_flags(section, field, default = None):
    """
    Read a list of quoted flags from `.buckconfig`.
    """

    val = native.read_config(section, field)
    if val != None:
        return shell.split(val)
    elif default != None:
        return default
    else:
        fail("`{}:{}`: no value set".format(section, field))

def read_boolean(section, field, default):
    val = native.read_config(section, field)
    if val != None:
        if val.lower() == "true":
            return True
        elif val.lower() == "false":
            return False
        else:
            fail("`{}:{}`: cannot coerce {} to bool".format(section, field, val))
    elif default == True or default == False:
        return default
    else:
        fail("`{}:{}`: no value set, requires bool".format(section, field))

def read_list(section, field, default, delimiter):
    val = native.read_config(section, field)
    if val != None:
        return [v.strip() for v in val.split(delimiter) if v]
    elif type(default) == type([]):
        return default
    else:
        fail("`{}:{}`: no value set, requires list delimited by {}".format(section, field, delimiter))

def read_string(section, field, default):
    return native.read_config(section, field, default)

def read_int(section, field, default):
    val = native.read_config(section, field)
    if val != None:
        return int(val)
    else:
        return default

def read_choice(section, field, choices, default = None):
    """
    Read a string from `.buckconfig` which can be one of the values given
    in `choices`.
    """

    val = native.read_config(section, field)
    if val != None:
        if val in choices:
            return val
        else:
            fail(
                "`{}:{}`: must be one of ({}), but was {!r}"
                    .format(section, field, ", ".join(choices), val),
            )
    elif default != None:
        return default
    else:
        fail(
            "`{}:{}`: no value set".format(section, field),
        )

def read_facebook_internal_string(section, field, default):
    return read_string(section, field, default)
