# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Simple module to create structs that are consumed by fbcode_macros//build_defs/build_mode.bzl
"""

""" The main modes that will usually be used """
default_modes = ['dbg', 'dev', 'dbgo', 'opt']

def create_build_mode(
        aspp_flags=(),
        cpp_flags=(),
        cxxpp_flags=(),
        c_flags=(),
        cxx_flags=(),
        ld_flags=(),
        clang_flags=(),
        gcc_flags=(),
        java_flags=(),
        dmd_flags=(),
        gdc_flags=(),
        ldc_flags=(),
        par_flags=(),
        ghc_flags=(),
        asan_options=(),
        ubsan_options=(),
        tsan_options=()):
    """
    Creates a new build mode struct that can modify flags for a specific path

    This is used in fbcode_macros//build_defs/build_mode.bzl and
    fbcode_macros//build_defs/build_mode_overrides.bzl

    Args:
        aspp_flags: flags for assembly source files
        cpp_flags: Preprocessor flags for C files
        cxxpp_flags: Preprocessor flags for C++ files
        c_flags: Additional compiler flags for C files
        cxx_flags: Additional compiler flags for C++ files
        ld_flags: Additional flags to pass to the linker
        clang_flags: Flags specific to clang. This should not be used if the
                    flag could be added to another group
        gcc_flags: Flags specific to gcc. This should not be used if the
                  flag could be added to another group
        java_flags: Extra flags to send to the java compiler
        dmd_flags: Extra D flags
        gdc_flags: Extra D flags
        ldc_flags: Extra D flags
        par_flags: Extra flags to send to PAR
        ghc_flags: Extra flags for the haskell compiler
        asan_options: Extra ASAN runtime options
        ubsan_options: Extra UBSAN runtime options
        tsan_options: Extra TSAN runtime options

    Returns:
        A struct with each of the provided fields, or () if the field was
        not provided
    """
    return struct(
        aspp_flags=aspp_flags,
        cpp_flags=cpp_flags,
        cxxpp_flags=cxxpp_flags,
        c_flags=c_flags,
        cxx_flags=cxx_flags,
        ld_flags=ld_flags,
        clang_flags=clang_flags,
        gcc_flags=gcc_flags,
        java_flags=java_flags,
        dmd_flags=dmd_flags,
        gdc_flags=gdc_flags,
        ldc_flags=ldc_flags,
        par_flags=par_flags,
        ghc_flags=ghc_flags,
        asan_options=asan_options,
        ubsan_options=ubsan_options,
        tsan_options=tsan_options,
    )
