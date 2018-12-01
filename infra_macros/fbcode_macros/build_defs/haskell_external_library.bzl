# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:haskell_common.bzl", "haskell_common")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def __get_identifier_from_db(name, version):
    """ Gets the package identifier from the path to the package database """

    package_glob = "lib/package.conf.d/{}-{}-*".format(name, version)
    files = native.glob([package_glob])
    if not files:
        fail("//{}:{}: cannot lookup package identifier: {} doesn\'t exist'".format(
            native.package_name(),
            name,
            package_glob,
        ))
    return paths.split_extension(paths.basename(files[0]))[0]

def haskell_external_library(
        name,
        version,
        db = None,
        id = None,
        include_dirs = (),
        lib_dir = None,
        libs = (),
        linker_flags = (),
        external_deps = (),
        visibility = None):
    """
    Wrapper for haskell_prebuilt_library

    Args:
        name: The name of the rule
        version: The version of this library
        db: The path to package.conf.d for this library
        id: The identifier for this library
        include_dirs: The directories to pull headers from
        lib_dir: If provided, a relative prefix that should be prepended to the static
                 and shared lib paths.
        libs: A list of shortnames of libraries that this rule relates to. These will
              be expanded into paths based on the lib_dir
        linker_flags: A list of additional flags that should be passed to the linker,
                      and exported
        external_deps: A list of external_dep strings/tuples that this library depends on
        visibility: The visibility of this rule. This may be modified by global rules.
    """
    visibility = get_visibility(visibility, name)
    package_name = native.package_name()
    platform = third_party.get_tp2_platform(package_name)

    exported_compiler_flags = [
        "-expose-package",
        "{}-{}".format(name, version),
    ]

    id = id or __get_identifier_from_db(name, version)

    exported_linker_flags = []

    # There are some cyclical deps between core haskell libs which prevent
    # us from using `--as-needed`.
    # TODO: Make this a more explicit setting
    if config.get_build_mode().startswith("dev"):
        exported_linker_flags.append("-Wl,--no-as-needed")
    for flag in linker_flags:
        exported_linker_flags.append("-Xlinker")
        exported_linker_flags.append(flag)

    prof = haskell_common.read_hs_profile()
    dbug = haskell_common.read_hs_debug()
    eventlog = haskell_common.read_hs_eventlog()

    # GHC's RTS requires linking against a different library depending
    # on what functionality is desired. We default to using the threaded
    # runtime, and reimplement the logic around what's allowed.
    if int(prof) + int(dbug) + int(eventlog) > 1:
        fail("Cannot mix profiling, debug, and eventlog. Pick one")

    static_libs = []
    profiled_static_libs = []

    # Special case rts
    if name == "rts":
        if dbug:
            libs = ["HSrts_thr_debug"]
        elif eventlog:
            libs = ["HSrts_thr_l"]

        # profiling is handled special since the _p suffix goes everywhere
        if prof:
            profiled_static_libs = [
                paths.join(lib_dir, "lib{}_p.a".format(l))
                for l in libs
            ]
        else:
            static_libs = [
                paths.join(lib_dir, "lib{}.a".format(l))
                for l in libs
            ]
    else:
        static_libs = [
            paths.join(lib_dir, "lib{}.a".format(l))
            for l in libs
        ]
        profiled_static_libs = [
            paths.join(lib_dir, "lib{}_p.a".format(l))
            for l in libs
        ]

    tp_config = third_party.get_third_party_config_for_platform(platform)
    ghc_version = tp_config["tools"]["projects"]["ghc"]
    shlibs = [
        paths.join(lib_dir, "lib{}-ghc{}.so".format(lib, ghc_version))
        for lib in libs
    ]
    shared_libs = {paths.basename(l): l for l in shlibs}

    dependencies = [
        src_and_dep_helpers.convert_external_build_target(target, platform = platform)
        for target in external_deps
    ]

    # Add the implicit dep to our own project rule.
    dependencies.append(
        target_utils.target_to_label(
            third_party.get_tp2_project_target(
                third_party.get_tp2_project_name(package_name),
            ),
            platform = platform,
        ),
    )

    fb_native.haskell_prebuilt_library(
        name = name,
        visibility = visibility,
        exported_compiler_flags = exported_compiler_flags,
        version = version,
        db = db,
        id = id,
        exported_linker_flags = exported_linker_flags,
        static_libs = static_libs,
        profiled_static_libs = profiled_static_libs,
        shared_libs = shared_libs,
        enable_profiling = True if prof else None,
        cxx_header_dirs = include_dirs,
        deps = dependencies,
    )
