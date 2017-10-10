#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import copy
import collections

# The high-level build mode object, which gives build flags a name
# and help message.
BuildMode = collections.namedtuple('BuildMode', ['help', 'settings'])

# The flags we can override.  These are exposed as makefile variables
# named BUILD_MODE_*.  Make sure these are consistent with the per-
# language rule generator code.
def BuildSettings(**kwargs):
    # A hack to support default arguments in namedtuples
    for field in _BuildSettings._fields:
        if field not in kwargs:
            kwargs[field] = []
    return _BuildSettings(**kwargs)


_BuildSettings = collections.namedtuple('BuildSettings', [
    # C/C++ family
    'ASPPFLAGS',
    'CPPFLAGS',
    'CXXPPFLAGS',
    'CFLAGS',
    'CXXFLAGS',
    'LDFLAGS',
    #Compiler specific C/C++ flags
    #A flag should not be added here if it could be added to another flag group
    'CLANGFLAGS',
    'GCCFLAGS',

    # Java
    'JAVAFLAGS',

    # D
    'DMDFLAGS',
    'GDCFLAGS',
    'LDCFLAGS',

    # Python PARs
    'PARFLAGS',

    # Haskel
    'GHCFLAGS',
])


def copy_mode(mode):
    """
    Return a copy the given build mode.  Use a deep copy so that flags
    can be appended to the new build mode.
    """

    return copy.deepcopy(mode)


DBG = BuildMode(help='debug build', settings=BuildSettings())
DEV = BuildMode(help='dev build', settings=BuildSettings())
DBGO = BuildMode(help='debug optimized build', settings=BuildSettings())
OPT = BuildMode(help='optimized build', settings=BuildSettings())

default_modes = {
    'dbg': DBG,
    'dbgo': DBGO,
    'dev': DEV,
    'opt': OPT,
}
