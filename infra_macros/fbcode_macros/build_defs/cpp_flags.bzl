load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_flags")

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

cpp_flags = struct(
    COMPILER_GENERAL_LANGS = _COMPILER_GENERAL_LANGS,
    COMPILER_LANGS = _COMPILER_LANGS,
    get_extra_cflags = _get_extra_cflags,
    get_extra_cppflags = _get_extra_cppflags,
    get_extra_cxxflags = _get_extra_cxxflags,
    get_extra_cxxppflags = _get_extra_cxxppflags,
    get_extra_ldflags = _get_extra_ldflags,
)
