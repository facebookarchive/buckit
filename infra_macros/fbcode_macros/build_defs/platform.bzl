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
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:config.bzl", "config")
load(
    "@fbcode_macros//build_defs/config:read_configs.bzl",
    "read_boolean",
    "read_string",
)
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

def _get_platform_overrides():
    """
    Gets a validated and modified version of platform_overrides

    Returns:
        Overrides in @fbcode_macros//build_defs:platform_overrides.bzl
        transformed by _transform_platform_overrides
    """
    return _platform_overrides

def _get_default_platform():
    """ Returns the default fbcode platform to use """
    return read_config("fbcode", "defaut_platform", "default")

def _get_platform_override():
    """ Returns the user-specified fbcode platform override """
    return read_config("fbcode", "platform")

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

    platform_override = _get_platform_override()
    if platform_override != None:
        return platform_override

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

    # If we require a platform to be found, fail at this point.
    if read_boolean("fbcode", "require_platform", False):
        fail(
          "Cannot find fbcode platform to use for architecture {}"
          .format(arch))

    return _get_default_platform()

def _to_buck_platform(platform, compiler):
    """
    Convert a given fbcode platform name into the Buck (C++) platform name.
    As the latter is compiler-family-specific, while the former is not, it
    at least takes into account the compiler chosen by the build mode.
    """

    fmt = read_string("fbcode", "buck_platform_format", "{platform}")
    return fmt.format(platform=platform, compiler=compiler)

def _get_buck_platform_for_base_path(base_path):
    """
    Return the Buck platform to use for a deployable rule at the given base
    path, running some consistency checks as well.
    """

    return _to_buck_platform(
        _get_platform_for_base_path(base_path),
        compiler.get_compiler_for_base_path(base_path))

def _get_buck_platform_for_current_buildfile():
    return _get_buck_platform_for_base_path(native.package_name())

def _get_fbcode_and_buck_platform_for_current_buildfile():
    """
    Returns both the general fbcode platform and the buck platform as a tuple

    The fbcode platform is used for things like paths and build info stamping
    The buck platform is used internally in buck to specify which toolchain
    settings to use.

    e.g. One might get gcc-5-glibc-2.23, gcc-5-glibc-2.23-clang back.
    gcc-5-glibc-2.23 would be used when finding third-party packages, but
    gcc-5-glibc-2.23-clang would be used in cxx_binary rules to force clang
    compiler and build flags to be used for a binary.

    This method just reduces some duplicate work that would be done if both
    get_platform_for_current_buildfile() and get_buck_platform_for_current_buildfile()
    were run.
    """
    package = native.package_name()
    fbcode_platform = _get_platform_for_base_path(package)
    buck_platform = _to_buck_platform(fbcode_platform, compiler.get_compiler_for_base_path(package))
    return fbcode_platform, buck_platform

platform = struct(
    get_buck_platform_for_base_path = _get_buck_platform_for_base_path,
    get_buck_platform_for_current_buildfile = _get_buck_platform_for_current_buildfile,
    get_default_platform = _get_default_platform,
    get_fbcode_and_buck_platform_for_current_buildfile = _get_fbcode_and_buck_platform_for_current_buildfile,
    get_platform_for_base_path = _get_platform_for_base_path,
    get_platform_for_cell_path_and_arch = _get_platform_for_cell_path_and_arch,
    get_platform_for_current_buildfile = _get_platform_for_current_buildfile,
    get_platform_overrides = _get_platform_overrides,
    to_buck_platform = _to_buck_platform,
)
