# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Helpers to discover information about platforms as defined by fbcode
"""

load("@fbcode_macros//build_defs/lib:fbcode_cxx_platforms.bzl", "fbcode_cxx_platforms")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbsource//tools/build_defs:host_arch.bzl", "host_arch")
load("@fbsource//tools/build_defs:host_os.bzl", "host_os")

def _build_all_platforms():
    """
    Build a list of all platform infos that the macro layer can support.
    """

    # Currently, we only support fbcode toolchains.
    return fbcode_cxx_platforms.PLATFORMS

def _pre_filter(platform):
    """
    Perform some filtering of supported platforms that can be done at global
    `.bzl` scope (i.e. cannot access `read_config()`).
    """

    # Filter out platforms that don't match the current host OS.
    if platform.host_arch != host_arch.HOST_ARCH_STR:
        return False

    # Filter out platforms that don't match the current host OS.
    if platform.host_os != host_os.HOST_OS_STR:
        return False

    return True

# Memoize some filtering we can do on the platform list that we can do at global
# scope (i.e. where we don't have access to `read_config()`) to avoid extra
# checks in `_get_platforms()`.
_MEMOIZED_PLATFORMS = [p for p in _build_all_platforms() if _pre_filter(p)]

def _filter(platform):
    """
    Perform some filtering of supported platforms that needs to be when
    evaluating BUCK files (i.e. needs access to `read_config()`).
    """

    # Filter out platforms that don't use supported compilers.
    if platform.compiler_family not in compiler.get_supported_compilers():
        return False

    return True

def _get_platforms():
    """
    Return platforms supported for this build.
    """

    return [p for p in _MEMOIZED_PLATFORMS if _filter(p)]

cxx_platforms = struct(
    get_platforms = _get_platforms,
)
