# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

""" Library to get common buck paths """

load("@bazel_skylib//lib:paths.bzl", "paths")

def _get_buck_out_path():
    """ Return the project-relative buck-out path """
    return native.read_config("project", "buck_out", "buck-out")

def _get_gen_path():
    """ Get the project-relative buck-out/gen path """
    return paths.join(_get_buck_out_path(), "gen")

# The string that can be used to refer to the current directory
_CURRENT_DIRECTORY = "."

common_paths = struct(
    get_buck_out_path = _get_buck_out_path,
    get_gen_path = _get_gen_path,
    CURRENT_DIRECTORY = _CURRENT_DIRECTORY,
)
