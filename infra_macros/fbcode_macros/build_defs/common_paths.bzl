# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

""" Library to get common buck paths """

load("@bazel_skylib//lib:paths.bzl", "paths")

def get_buck_out_path():
    """ Return the project-relative buck-out path """
    return read_config("project", "buck_out", "buck-out")

def get_gen_path():
    """ Get the project-relative buck-out/gen path """
    return paths.join(get_buck_out_path(), "gen")
