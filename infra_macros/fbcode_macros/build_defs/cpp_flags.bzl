load("@bazel_skylib//lib:partial.bzl", "partial")
load("@fbcode_macros//build_defs:build_mode.bzl", _build_mode = "build_mode")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_flags", "read_int")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")

# The languages which general compiler flag apply to.
_COMPILER_LANGS = (
    "asm",
    "assembler",
    "c_cpp_output",
    "cuda_cpp_output",
    "cxx_cpp_output",
)

# The languages which general compiler flag apply to.
_COMPILER_GENERAL_LANGS = ("assembler", "c_cpp_output", "cxx_cpp_output")

def _get_extra_cflags():
    """
    Get extra C compiler flags to build with.
    """

    return read_flags("cxx", "extra_cflags", default = ())

def _get_extra_cxxflags():
    """
    Get extra C++ compiler flags to build with.
    """

    return read_flags("cxx", "extra_cxxflags", default = ())

def _get_extra_cppflags():
    """
    Get extra C preprocessor flags to build with.
    """

    return read_flags("cxx", "extra_cppflags", default = ())

def _get_extra_cxxppflags():
    """
    Get extra C++ preprocessor flags to build with.
    """

    return read_flags("cxx", "extra_cxxppflags", default = ())

def _get_extra_ldflags():
    """
    Get extra linker flags to build with.
    """

    return read_flags("cxx", "extra_ldflags", default = ())

def _get_compiler_flags_partial(build_mode, _, compiler):
    return build_mode.gcc_flags if compiler == "gcc" else build_mode.clang_flags

def _get_compiler_flags(base_path):
    """
    Return a dict mapping languages to base compiler flags.

    Returns:
        A dictionary of language -> [(platform regex, [flags])]
        See https://buckbuild.com/rule/cxx_library.html#lang_platform_preprocessor_flags
    """

    # Initialize the compiler flags dictionary.
    compiler_flags = {lang: [] for lang in _COMPILER_LANGS}

    # The set of language we apply "general" compiler flags to.
    c_langs = _COMPILER_GENERAL_LANGS

    # Apply the general sanitizer/coverage flags.
    per_platform_sanitizer_flags = []
    if sanitizers.get_sanitizer() != None:
        per_platform_sanitizer_flags = src_and_dep_helpers.format_platform_param(
            sanitizers.get_sanitizer_flags(),
        )
    per_platform_coverage_flags = src_and_dep_helpers.format_platform_param(
        coverage.get_coverage_flags(base_path),
    )

    for lang in c_langs:
        if per_platform_sanitizer_flags != None:
            compiler_flags[lang].extend(per_platform_sanitizer_flags)
        compiler_flags[lang].extend(per_platform_coverage_flags)

    # Apply flags from the build mode file.
    build_mode = _build_mode.get_build_mode_for_base_path(base_path)
    if build_mode != None:
        compiler_partial = partial.make(_get_compiler_flags_partial, build_mode)

        # Apply language-specific build mode flags.
        compiler_flags["c_cpp_output"].extend(
            src_and_dep_helpers.format_platform_param(build_mode.c_flags),
        )
        compiler_flags["cxx_cpp_output"].extend(
            src_and_dep_helpers.format_platform_param(build_mode.cxx_flags),
        )

        # Apply compiler-specific build mode flags.
        for lang in c_langs:
            compiler_flags[lang].extend(
                src_and_dep_helpers.format_platform_param(compiler_partial),
            )

        # Cuda always uses GCC.
        compiler_flags["cuda_cpp_output"].extend(
            src_and_dep_helpers.format_platform_param(build_mode.gcc_flags),
        )

    # Add in command line flags last.
    compiler_flags["c_cpp_output"].extend(
        src_and_dep_helpers.format_platform_param(_get_extra_cflags()),
    )
    compiler_flags["cxx_cpp_output"].extend(
        src_and_dep_helpers.format_platform_param(_get_extra_cxxflags()),
    )

    return compiler_flags

def _get_lto_level():
    """
    Returns the user-specific LTO parallelism level.
    """

    default = 32 if config.get_lto_type() else 0
    return read_int("cxx", "lto", default)

def _get_lto_is_enabled():
    """
    Returns whether to use LTO for this build.
    """

    return _get_lto_level() > 0

def _get_gcc_lto_ldflags(base_path, platform):
    """
    Get linker flags required for gcc LTO.

    Args:
        base_path: The package path
        platform: The fbcode platform in use
    """

    flags = []

    lto_type = config.get_lto_type()

    # Verify we're running with a build mode that supports LTO.
    if lto_type != "fat":
        fail("build mode doesn't support {} LTO".format(lto_type))

    # Read the LTO parallelism level from the config, where `0` disables
    # LTO.
    lto_level = _get_lto_level()
    if lto_level <= 0:
        fail("lto_level was {}, must be greater than zero".format(lto_level))

    # When linking with LTO, we need to pass compiler flags that affect
    # code generation back into the linker.  Since we don't actually
    # discern code generation flags from language specific flags, just
    # pass all our C/C++ compiler flags in.
    buck_platform = platform_utils.to_buck_platform(platform, "gcc")
    compiler_flags = _get_compiler_flags(base_path)
    section = "cxx#{}".format(buck_platform)
    flags.extend(read_flags(section, "cflags", []))
    for plat_re, cflags in compiler_flags["c_cpp_output"]:
        if buck_platform in plat_re:
            flags.extend(cflags)
    flags.extend(read_flags(section, "cxxflags", []))
    for plat_re, cflags in compiler_flags["cxx_cpp_output"]:
        if buck_platform in plat_re:
            flags.extend(cflags)

    flags.extend([
        # Some warnings that only show up at lto time.
        "-Wno-free-nonheap-object",
        "-Wno-odr",
        "-Wno-lto-type-mismatch",

        # Set the linker that flags that will run LTO.
        "-fuse-linker-plugin",
        "-flto={}".format(lto_level),
        "--param=lto-partitions={}".format(lto_level * 2),
    ])

    return flags

cpp_flags = struct(
    COMPILER_LANGS = _COMPILER_LANGS,
    get_compiler_flags = _get_compiler_flags,
    get_extra_cflags = _get_extra_cflags,
    get_extra_cppflags = _get_extra_cppflags,
    get_extra_cxxflags = _get_extra_cxxflags,
    get_extra_cxxppflags = _get_extra_cxxppflags,
    get_extra_ldflags = _get_extra_ldflags,
    get_gcc_lto_ldflags = _get_gcc_lto_ldflags,
    get_lto_is_enabled = _get_lto_is_enabled,
)
