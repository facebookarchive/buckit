# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def rust_external_library(
        name,
        rlib = None,
        crate = None,
        deps = (),
        licenses = (),
        visibility = None,
        external_deps = ()):
    """
    Represents an prebuilt third-party rust library

    Args:
        name: The name of the rule
        rlib: Path to the precompiled rust crate
        crate: See https://buckbuild.com/rule/prebuilt_rust_library.html#crate
        deps: See https://buckbuild.com/rule/prebuilt_rust_library.html#deps
        licenses: See https://buckbuild.com/rule/prebuilt_rust_library.html#licenses
        visibility: The visibility for the rule, modified by the path
        external_deps: The other third-party dependencies for this rule. See cxx_*
                       rules for details on the format
    """
    visibility = get_visibility(visibility, name)
    package = native.package_name()
    platform = third_party.get_tp2_platform(package)

    dependencies = [
        target_utils.parse_target(dep, default_base_path = package)
        for dep in deps
    ]

    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))
    if dependencies:
        dependencies = src_and_dep_helpers.format_deps(dependencies, platform = platform)

    fb_native.prebuilt_rust_library(
        name = name,
        rlib = rlib,
        crate = crate,
        licenses = licenses,
        visibility = visibility,
        deps = dependencies,
    )
