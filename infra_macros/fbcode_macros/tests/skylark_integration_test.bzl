# Copyright 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Rules to help run integration tests for extension files
"""

def targets_to_resource_paths(targets):
    """
    Converts a list of targets into a {resource_name: target} mapping
    """
    return {target_to_resource_path(target): target for target in targets}

def target_to_resource_path(target):
    """
    Converts a resource name to a flattened path.

    Example:
        target_to_resource_path("fbcode_macros//build_defs:config.bzl") returns
        "fbcode_macros/build_defs/config.bzl

    Args:
        target: A fully qualified target string (including full path and cell)

    Returns:
        A path where the cell is turned into a top level directory, and
        the portion after the ':' is turned into a filename.

    """
    return target.replace("//", "/").replace(":", "/")

def skylark_integration_test(name, deps=None, resources=None, **kwargs):
    """
    Helps run integration tests to test .bzl files

    This rule is mostly a wrapper around python_test that adds the correct
    dependencies and resources needed to utilize an integration testing
    framework found in fbcode_macros//tests/utils.py. See
    fbcode_macros//tests:config_test for an example.

    These integration tests take two forms, simple evaluation of statements,
    and evaluation and comparison of full build files. This is acheived by
    running buck directly to evaluate outputs. This also runs both the python
    interpreter, and the skylark interpreter for the same rules and verifies
    that they both pass the tests

    Note that resources that are added will be put in a directory according to
    their cell and path. That is, fbcode_macros//build_defs:config.bzl is
    available at fbcode_macros/build_defs/config.bzl in the test. If a
    cell is created in the test, it will look in this directory to populate
    which macros should be available to tests.

    Example:
        skylark_integration_test(
            name = "read_config_test",
            resources = XPLAT_RESOURCES + ["xplat//config:read_config.bzl"],
            srcs = ["read_config_test.py"],
        )

    Args:
        name: The name of the rule
        deps: A normal list of deps for python_test
        resources: If a list is provided, convert the destination paths as
                   above. If a dictionary is provided, paths will not be changed
        **kwargs: Arguments to pass to python_test
    """
    deps = deps or []
    resources = resources or []
    deps.append("fbcode_macros//tests:utils")
    if type(resources) == type(list):
        resources = {
            target_to_resource_path(target): target for target in resources
        }

    native.python_test(
        name = name,
        deps = deps,
        resources = resources,
        **kwargs
    )
