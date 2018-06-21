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

load("@fbcode_macros//build_defs:build_mode_overrides.bzl", "build_mode_overrides")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@bazel_skylib//lib:paths.bzl", "paths")

def _get_build_modes_for_base_path(base_path):
    """ Returns `get_build_modes_for_cell_and_base_path()` for the specified base_path """
    return _get_build_modes_for_cell_and_base_path(
        config.get_current_repo_name(),
        base_path,
    )

def _get_build_modes_for_current_buildfile():
    """ Returns `get_build_modes_for_cell_and_base_path()` for the build file that calls this method """
    return _get_build_modes_for_cell_and_base_path(
        config.get_current_repo_name(),
        native.package_name(),
    )

def _get_build_mode_for_base_path(base_path):
    """
    Returns `get_build_modes_for_cell_and_base_path()` for the build file and
    that calls this method and the current build mode
    """
    return _get_build_modes_for_base_path(base_path).get(config.get_build_mode())

def _get_build_modes_for_cell_and_base_path(cell, path):
    """
    Get the build modes for a given cell and path (and subpaths) within that cell

    Args:
        cell: The cell name (specified by buckconfig value fbcode.current_repo)
        path: The relative path within the repository. This should not include
              any file names, just the directory

    Returns:
        A dictionary of mode name -> structs containing additional flags. e.g.
        one might return {"dev": create_build_mode(CFLAGS=["-DDEBUG"])}

        NOTE: This will invoke a method at runtime because some build mode
              definiitions require a build file context (e.g. for read_config)
    """
    per_cell_overrides = build_mode_overrides.get(cell)
    if per_cell_overrides != None:
        # Make "foo" loop twice. Once for "foo", once for "". foo/bar gets you
        # foo/bar, foo, and ""
        count = path.count("/") + 2
        for _ in range(count):
            ret = per_cell_overrides.get(path)
            if ret != None:
                return ret()
            path = paths.dirname(path)
    return {}

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
    get_build_mode_for_base_path = _get_build_mode_for_base_path,
    get_build_mode_overrides = _get_build_mode_overrides,
    get_build_modes_for_base_path = _get_build_modes_for_base_path,
    get_build_modes_for_cell_and_base_path = _get_build_modes_for_cell_and_base_path,
    get_build_modes_for_current_buildfile = _get_build_modes_for_current_buildfile,
)
