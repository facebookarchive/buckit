load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_string", "is_unicode")
load("@fbcode_macros//build_defs:auto_pch_blacklist.bzl", "auto_pch_blacklist")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")

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
    if not is_string(filename) and not is_unicode(filename):
        return False
    for ext in _CPP_SOURCE_EXTS:
        if filename.endswith(ext):
            return True
    return False

def _get_fbcode_default_pch(srcs, base_path, name):
    """
    Determine a default precompiled_header rule to use for a specific C++ rule.

    Args:
        srcs: A list of sources that are used by the original rule to ensure that
              PCH is not used for non-C++ sources
        base_path: The package that the C++ rule is in
        name: The name of the C++ rule

    Returns:
        `None` if no default PCH configured / applicable to this rule, otherwise the
        rule to use for precompiled_header
        (see https://buckbuild.com/rule/cxx_library.html#precompiled_header)
    """

    # No sources to compile?  Then no point in precompiling.
    if not srcs:
        return None

    # Don't mess with core tools + deps (mainly to keep rule keys stable).
    if _exclude_from_auto_pch(base_path, name):
        return None

    # Don't allow this to be used for anything non-C++.
    has_only_cpp_srcs = all([_is_cpp_source(s) for s in srcs])
    if not has_only_cpp_srcs:
        return None

    # Return the default PCH setting from config (`None` if absent).
    ret = native.read_config("fbcode", "default_pch", None)

    # Literally the word 'None'?  This is to support disabling via command
    # line or in a .buckconfig from e.g. a unit test (see lua_cpp_main.py).
    if ret == "None":
        ret = None
    return ret

def _exclude_from_auto_pch(base_path, name):
    """
    Some cxx_library rules should not get PCHs auto-added; for the most
    part this is for core tools and their dependencies, so we don't
    change their rule keys.
    """
    if core_tools.is_core_tool(base_path, name):
        return True
    path = base_path.split("//", 1)[-1]

    if not path:
        return True
    path += "/"

    slash_idx = len(path)
    for _ in range(slash_idx):
        if slash_idx == -1:
            break
        if sets.contains(auto_pch_blacklist, path[:slash_idx]):
            return True
        slash_idx = path.rfind("/", 0, slash_idx)

    # No reason to disable auto-PCH, that we know of.
    return False

cpp_common = struct(
    SOURCE_EXTS = _SOURCE_EXTS,
    default_headers_library = _default_headers_library,
    exclude_from_auto_pch = _exclude_from_auto_pch,
    get_fbcode_default_pch = _get_fbcode_default_pch,
    is_cpp_source = _is_cpp_source,
)
