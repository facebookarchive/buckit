# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Helper methods to support the notion of 'BUILD_MODE' files

BUILD_MODE files are those that modify compiler flags in a subtree based on
the 'mode' that the build was run in
"""

load("@fbcode_macros//build_defs:config.bzl", "config")

def _get_build_modes_for_current_buildfile():
    """ Returns `get_build_modes_for_cell_and_base_path()` for the build file that calls this method """
    mode_callable = native.implicit_package_symbol("get_modes", None)
    if mode_callable:
        return mode_callable()
    else:
        return {}

def _get_build_mode_for_current_buildfile():
    return _get_build_modes_for_current_buildfile().get(config.get_build_mode())

def _get_build_mode_overrides():
    """ Materializes all build modes for the current context """
    return {
        cell: {
            path: get_build_mode()
            for path, get_build_mode in cell_values.items()
        }
        for cell, cell_values in build_mode_overrides.items()
    }

build_mode = struct(
    get_build_mode_overrides = _get_build_mode_overrides,
    get_build_modes_for_current_buildfile = _get_build_modes_for_current_buildfile,
    get_build_mode_for_current_buildfile = _get_build_mode_for_current_buildfile,
)
