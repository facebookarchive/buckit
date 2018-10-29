# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Function used to re-export files
"""

load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load(
    "@fbcode_macros//build_defs:python_typing.bzl",
    "gen_typing_config",
    "get_typing_config_target",
)

def export_files(files, visibility = None, mode = "reference"):
    """ Takes a list of files, and exports each of them """
    for file in files:
        fb_native.export_file(
            name = file,
            visibility = get_visibility(visibility, file),
            mode = mode,
        )

def buck_export_file(name, visibility = None, *args, **kwargs):
    """ Proxy for native.export file """
    fb_native.export_file(
        name = name,
        visibility = get_visibility(visibility, name),
        *args,
        **kwargs
    )

def export_file(
        name,
        visibility = None,
        mode = "reference",
        create_typing_rule = True,
        *args,
        **kwargs):
    """
    Proxy for native.export file using reference mode by default

    Args:
      name: The name of the exported file. This will also be used for child
            rules if create_typing_rule is True
      visibility: Normal visibility rules
      mode: The mode for the export_file call. Defaults to reference
      create_typing_rule: Whether or not to create a companion python typing
                          rule. This is necessary so that parent rules that
                          have a -typing suffix that depend on exported files
                          can blindly depend on '-typing' suffixed rules.
                          This will likely go away in the future.
    """
    visibility = get_visibility(visibility, name)
    if create_typing_rule and get_typing_config_target():
        gen_typing_config(target_name = name, visibility = visibility)
    fb_native.export_file(
        name = name,
        mode = mode,
        visibility = visibility,
        *args,
        **kwargs
    )
