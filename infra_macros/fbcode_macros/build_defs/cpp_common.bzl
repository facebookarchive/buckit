load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")

_C_SOURCE_EXTS = (
    ".c",
)

_CPP_SOURCE_EXTS = (
    ".cc",
    ".cpp",
)

_SOURCE_EXTS = _C_SOURCE_EXTS + _CPP_SOURCE_EXTS

_HEADER_EXTS = (
    ".h",
    ".hh",
    ".tcc",
    ".hpp",
    ".cuh",
)

_DEFAULT_HEADERS_RULE_NAME = "__default_headers__"

_DEFAULT_HEADERS_RULE_TARGET = ":__default_headers__"

_DEFAULT_HEADERS_GLOB_PATTERN = ["**/*" + ext for ext in _HEADER_EXTS]

def _default_headers_library():
    """
    Rule that globs on all headers recursively. Ensures that it is only created once per package.

    Outputs:
        __default_headers__: The rule that globs on all headers

    Returns:
        The target of the rule that was created or existed already
    """
    if native.rule_exists(_DEFAULT_HEADERS_RULE_NAME):
        return _DEFAULT_HEADERS_RULE_TARGET

    buck_platform = platform_utils.get_buck_platform_for_current_buildfile()
    fb_native.cxx_library(
        name = _DEFAULT_HEADERS_RULE_NAME,
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
        exported_headers = native.glob(_DEFAULT_HEADERS_GLOB_PATTERN),
    )
    return _DEFAULT_HEADERS_RULE_TARGET

def _is_cpp_source(filename):
    """ Whether the specified `filename` looks like a c++ source """
    for ext in _CPP_SOURCE_EXTS:
        if filename.endswith(ext):
            return True
    return False

cpp_common = struct(
    SOURCE_EXTS = _SOURCE_EXTS,
    default_headers_library = _default_headers_library,
    is_cpp_source = _is_cpp_source,
)
