# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Functions that handle correcting 'visiblity' arguments
"""

load("@fbcode_macros//build_defs:visibility_exceptions.bzl", "WHITELIST")

def get_visibility_for_base_path(visibility_attr, name_attr, base_path):
    """
    Gets the default visibility for a given base_path.

    If the base_path is an experimental path and isn't in a whitelist, this
    ensures that the target is only visible to the experimental directory.
    Otherwise, this returns either a default visibility if visibility_attr's
    value is None, or returns the original value.

    Args:
        visibility_attr: The value of the rule's 'visibility' attribute, or None
        name_attr: The name of the rule
        base_path: The base path to the package that the target resides in.
                   This will eventually be removed, and native.package() will
                   be used instead.

    Returns:
        A visibility array
    """
    if (base_path.startswith("experimental/") and
        (base_path, name_attr) not in WHITELIST):
        return ["//experimental/..."]

    if visibility_attr == None:
        return ["PUBLIC"]
    else:
        return visibility_attr

def get_visibility(visibility_attr, name_attr):
    """
    Returns either the provided visibility list, or a default visibility if None
    """
    return get_visibility_for_base_path(
        visibility_attr,
        name_attr,
        native.package_name(),
    )
