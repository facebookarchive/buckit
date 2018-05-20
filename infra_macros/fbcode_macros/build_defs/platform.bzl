# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Helpers to discover information about platforms as defined by fbcode
"""

load("@fbcode_macros//build_defs:third_party_config.bzl", "third_party_config")
load("@fbcode_macros//build_defs:platform_overrides.bzl", "platform_overrides")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_boolean")
load("@bazel_skylib//lib:paths.bzl", "paths")

def __get_current_architecture():
    arch = native.host_info().arch
    if arch.is_x86_64:
        return "x86_64"
    elif arch.is_aarch64:
        return "aarch64"
    else:
        fail("Current host architecture (%s) is unsupported" % arch)

_all_platforms = third_party_config["platforms"].keys()
_current_architecture = __get_current_architecture()

def _transform_platform_overrides(cell_to_path_to_platforms_mapping):
    """
    Takes a mapping of cell/path/platform and validates and transforms it

    The original form: {cell: {path: [plat1, plat2]}} is turned into
    {cell: {path: {arch1: plat1, arch2: plat2}}}. Platforms are also
    validated to ensure that they are present in the overal configuration

    Fails if a platform is invalid or if no platforms are present for
    a given directory

    Args:
        cell_to_path_to_platforms_mapping: A mapping of {cell: {path:
                                            [platform...]}} as described above

    Returns:
        A validated mapping of {cell: {path: {arch: platform}}}, with
        architectures omitted if they don't have any platforms
    """
    ret = {}
    for cell, paths_to_platforms in cell_to_path_to_platforms_mapping.items():
        ret[cell] = {}
        for path, platforms in paths_to_platforms.items():
            for platform in platforms:
                if platform not in third_party_config["platforms"]:
                    fail(
                        "Path %s has invalid platform %s. Must be one of %s" % (
                            path,
                            platform,
                            ", ".join(sorted(_all_platforms)),
                        ),
                    )
                platform_arch = \
                    third_party_config["platforms"][platform]["architecture"]
                if path not in ret[cell]:
                    ret[cell][path] = {}
                    ret[cell][path][platform_arch] = platform
                    continue

                if platform_arch in ret[cell][path]:
                    fail(
                        "Path %s has both platform %s and %s for architecture %s" % (
                            path,
                            ret[cell][path][platform_arch],
                            platform,
                            platform_arch,
                        ),
                    )
                else:
                    ret[cell][path][platform_arch] = platform
    return ret

_platform_overrides = _transform_platform_overrides(platform_overrides)

def _get_use_platform_files():
    """
    Determines whether platform files should be used, or just the default
    """
    return read_boolean("fbcode", "platform_files", True)

def _get_platform_overrides():
    """
    Gets a validated and modified version of platform_overrides

    Returns:
        Overrides in @fbcode_macros//build_defs:platform_overrides.bzl
        transformed by _transform_platform_overrides
    """
    return _platform_overrides

def _get_default_platform():
    """ Returns the default cxx platform to use """
    if config.get_require_platform():
        return read_config("fbcode", "platform")
    else:
        return read_config("cxx", "default_platform", "default")

def _get_platform_for_base_path(base_path):
    """
    Returns `get_platform_for_cell_path_and_arch()` for the given base_path

    Args:
      base_path: The base path within the default repository
    """
    return _get_platform_for_cell_path_and_arch(
        config.get_current_repo_name(),
        base_path,
        _current_architecture,
    )

def _get_platform_for_current_buildfile():
    """  Returns `get_platform_for_cell_path_and_arch()` for the build file that calls this method """
    return _get_platform_for_cell_path_and_arch(
        config.get_current_repo_name(),
        native.package_name(),
        _current_architecture,
    )

def _get_platform_for_cell_path_and_arch(cell, path, arch):
    """
    Get the platform for a given cell and path within that cell.

    Args:
        cell: The cell name (specifed by buckconfig value fbcode.current_repo)
        path: The relative path within the repository. This should not include
               any file names, just the directory
        arch: An architecture string. This is x86_64 or aarch64 right now

    Returns:
        The deepest nested subdirectory from
        @fbcode_macros//build_defs:platform_overrides.bzl that matches `path`
        and is valid for the current host architecture. If nothing matches, the
        default platform is returned
    """
    if not _get_use_platform_files():
        return _get_default_platform()

    per_cell_overrides = _platform_overrides.get(cell)
    if per_cell_overrides != None:
        # Make "foo" loop twice. Once for "foo", once for "". foo/bar gets you
        # foo/bar, foo, and ""
        count = path.count("/") + 2
        for _ in range(count):
            ret = per_cell_overrides.get(path)
            if ret != None and arch in ret:
                return ret[arch]
            path = paths.dirname(path)

    return _get_default_platform()

platform = struct(
    get_default_platform = _get_default_platform,
    get_platform_for_current_buildfile = _get_platform_for_current_buildfile,
    get_platform_for_base_path = _get_platform_for_base_path,
    get_platform_for_cell_path_and_arch = _get_platform_for_cell_path_and_arch,
    get_platform_overrides = _get_platform_overrides,
)
