# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Simple module to create structs that are consumed by fbcode_macros//build_defs/build_mode.bzl
"""

# The main modes that will usually be used
default_modes = [
    "dbg",
    "dev",
    "dbgo",
    "opt",
]

def create_build_mode(
        aspp_flags = (),
        cpp_flags = (),
        cxxpp_flags = (),
        c_flags = (),
        cxx_flags = (),
        ld_flags = (),
        clang_flags = (),
        gcc_flags = (),
        java_flags = (),
        dmd_flags = (),
        gdc_flags = (),
        ldc_flags = (),
        par_flags = (),
        ghc_flags = (),
        asan_options = (),
        ubsan_options = (),
        tsan_options = (),
        lsan_suppressions = (),
        compiler = None,
        cxx_modules = None,
        cxx_compile_with_modules = None):
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
        lsan_suppressions: LSAN suppressions
        compiler: Use this compiler for deployable rules under this directory,
                  for build modes which don't globally set the compiler family
                  choice. Example inputs: 'clang', or 'gcc'.
        cxx_modules: Whether to build a rule's C/C++ headers into clang modules
                     by default in modular builds.
        cxx_compile_with_modules: Whether to build a rule's C/C++ sources using
                                  clang modules by default in modular builds.

    Returns:
        A struct with each of the provided fields, or () if the field was
        not provided
    """
    return struct(
        asan_options = asan_options,
        aspp_flags = aspp_flags,
        c_flags = c_flags,
        clang_flags = clang_flags,
        compiler = compiler,
        cpp_flags = cpp_flags,
        cxx_flags = cxx_flags,
        cxx_modules = cxx_modules,
        cxx_compile_with_modules = cxx_compile_with_modules,
        cxxpp_flags = cxxpp_flags,
        dmd_flags = dmd_flags,
        gcc_flags = gcc_flags,
        gdc_flags = gdc_flags,
        ghc_flags = ghc_flags,
        java_flags = java_flags,
        ld_flags = ld_flags,
        ldc_flags = ldc_flags,
        lsan_suppressions = lsan_suppressions,
        par_flags = par_flags,
        tsan_options = tsan_options,
        ubsan_options = ubsan_options,
    )

def _combine(lhs, rhs):
    """
    Combines a list, tuple, or dict, with another list or tuple or dict

    Build mode struct attributes are tuples by default, but many consumers
    use the 'create_build_mode' function to initialize them to lists, or
    even dictionaries. When combining build modes using the 'extend_build_mode'
    function, this helper function handles the case in which a list is
    extended with a tuple argument, or vice versa

    Args:
        lhs: A tuple, list, or dict
        rhs: A tuple, list, or dict to add to the left hand argument

    Returns:
        A value of the lhs argument's type, with the elements from the rhs
        added to it
    """
    if not rhs:
        return lhs

    # Note: 'isinstance' and 'issubclass' are not available in this environment,
    # so we check here for the exact type. Subclasses will not pass this check.
    if type(lhs) == type({}):
        result = {}
        result.update(lhs)
        result.update(rhs)
        return result
    elif type(lhs) == type([]):
        return lhs + list(rhs)
    elif type(lhs) == type(()):
        return lhs + tuple(rhs)
    return lhs + rhs

def extend_build_mode(
        build_mode,
        aspp_flags = (),
        cpp_flags = (),
        cxxpp_flags = (),
        c_flags = (),
        cxx_flags = (),
        ld_flags = (),
        clang_flags = (),
        gcc_flags = (),
        java_flags = (),
        dmd_flags = (),
        gdc_flags = (),
        ldc_flags = (),
        par_flags = (),
        ghc_flags = (),
        asan_options = (),
        ubsan_options = (),
        tsan_options = (),
        lsan_suppressions = (),
        compiler = None,
        cxx_modules = None,
        cxx_compile_with_modules = None):
    """
    Creates a new build mode struct with the given flags added to it

    You may use this in your BUILD_MODE.bzl files in order to "extend" a
    build mode struct from a parent path

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
        lsan_suppressions: LSAN suppressions
        compiler: Use this compiler for deployable rules under this directory,
                  for build modes which don't globally set the compiler family
                  choice. Example inputs: 'clang', or 'gcc'.
        cxx_modules: Whether to enable/disable clang modules on the rules
                     covered by this build mode file by default in modular
                     builds.
        cxx_compile_with_modules: Whether to build a rule's C/C++ sources using
                                  clang modules by default in modular builds.

    Returns:
        A struct with each of the given build mode struct's fields, with the
        given fields added to each of them. If compiler is provided, it is
        used instead of the compiler specified by the given build mode
    """
    new_compiler = build_mode.compiler
    if compiler:
        new_compiler = compiler
    new_cxx_modules = build_mode.cxx_modules
    if cxx_modules != None:
        new_cxx_modules = cxx_modules
    new_cxx_compile_with_modules = build_mode.cxx_compile_with_modules
    if cxx_compile_with_modules != None:
        new_cxx_compile_with_modules = cxx_compile_with_modules
    return struct(
        asan_options = _combine(build_mode.asan_options, asan_options),
        aspp_flags = _combine(build_mode.aspp_flags, aspp_flags),
        c_flags = _combine(build_mode.c_flags, c_flags),
        clang_flags = _combine(build_mode.clang_flags, clang_flags),
        compiler = new_compiler,
        cpp_flags = _combine(build_mode.cpp_flags, cpp_flags),
        cxx_flags = _combine(build_mode.cxx_flags, cxx_flags),
        cxx_modules = new_cxx_modules,
        cxx_compile_with_modules = new_cxx_compile_with_modules,
        cxxpp_flags = _combine(build_mode.cxxpp_flags, cxxpp_flags),
        dmd_flags = _combine(build_mode.dmd_flags, dmd_flags),
        gcc_flags = _combine(build_mode.gcc_flags, gcc_flags),
        gdc_flags = _combine(build_mode.gdc_flags, gdc_flags),
        ghc_flags = _combine(build_mode.ghc_flags, ghc_flags),
        java_flags = _combine(build_mode.java_flags, java_flags),
        ld_flags = _combine(build_mode.ld_flags, ld_flags),
        ldc_flags = _combine(build_mode.ldc_flags, ldc_flags),
        lsan_suppressions = _combine(build_mode.lsan_suppressions, lsan_suppressions),
        par_flags = _combine(build_mode.par_flags, par_flags),
        tsan_options = _combine(build_mode.tsan_options, tsan_options),
        ubsan_options = _combine(build_mode.ubsan_options, ubsan_options),
    )
