load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@bazel_skylib//lib:partial.bzl", "partial")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_dict", "is_string", "is_unicode")
load("@fbcode_macros//build_defs:build_mode.bzl", _build_mode = "build_mode")
load("@fbcode_macros//build_defs:auto_pch_blacklist.bzl", "auto_pch_blacklist")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")

_SourceWithFlags = provider(fields = [
    "src",
    "flags",
])

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

# PLEASE DON'T UPDATE WITHOUT REACHING OUT TO FBCODE FOUNDATION FIRST.
# Using arbitrary linker flags in libraries can cause unexpected issues
# for upstream dependencies, so we make sure to restrict to a safe(r)
# subset of potential flags.
_VALID_LINKER_FLAG_PREFIXES = (
    "-L",
    "-u",
    "-rpath",
    "--wrap",
    "--dynamic-list",
    "--export-dynamic",
    "--enable-new-dtags",
)

_VALID_PREPROCESSOR_FLAG_PREFIXES = ("-D", "-I")

_INVALID_PREPROCESSOR_FLAG_PREFIXES = ("-I/usr/local/include", "-I/usr/include")

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

def _assert_linker_flags(flags):
    """
    Verifies that linker flags match a whilelist

    This fails the build if an invalid linker flag is provided

    Args:
        flags: A list of linker flags
    """
    for flag in flags:
        if not flag.startswith(_VALID_LINKER_FLAG_PREFIXES):
            fail("using disallowed linker flag in a library: " + flag)

def _assert_preprocessor_flags(param, flags):
    """
    Make sure the given flags are valid preprocessor flags.

    This fails the build if any invalid flags are provided

    Args:
        param: The name of the paramter that is using these flags. Used for error messages
        flags: A list of preprocessor flags
    """

    # Check that we're getting an actual preprocessor flag (e.g. and not a
    # compiler flag).
    for flag in flags:
        if not flag.startswith(_VALID_PREPROCESSOR_FLAG_PREFIXES):
            fail(
                "`{}`: invalid preprocessor flag (expected `-[DI]*`): {}".format(param, flag),
            )

    # Check for includes pointing to system paths.
    bad_flags = [
        flag
        for flag in flags
        # We already filter out -isystem above, and we shouldn't really have absolute
        # paths to include directories
        # We filter on ending with 'include' right now, because there are a couple of
        # dirs we accept (namely a JDK include dir that ends in include/linux) that
        # should not get caught here
        if flag.startswith(_INVALID_PREPROCESSOR_FLAG_PREFIXES)
    ]
    if bad_flags:
        fail(
            ('The flags \"{}\" in \'{}\' would pull in ' +
             "system include paths which could cause incompatible " +
             "header files to be used instead of correct versions from " +
             "third-party.")
                .format(" ".join(bad_flags), param),
        )

def _format_source_with_flags(src_with_flags, platform = None):
    """
    Format a `SourceWithFlags` object into a label useable by buck native rules

    Args:
        srcs_with_flags: A `SourceWithFlags` object
        platform: If provided, use this to format the source component of
                  `srcs_with_flags` into a buck label

    Returns:
        Either a tuple of (<buck label>, [<flags for this source file>]) or just the
        buck label if no flags were provided for this source
    """

    src = src_and_dep_helpers.format_source(src_with_flags.src, platform = platform)
    return (src, src_with_flags.flags) if src_with_flags.flags else src

def _format_source_with_flags_list_partial(tp2_dep_srcs, platform, _):
    return [
        _format_source_with_flags(src, platform = platform)
        for src in tp2_dep_srcs
    ]

def _format_source_with_flags_list(srcs_with_flags):
    """
    Convert the provided SourceWithFlags objects into objects useable by buck native rules

    Args:
        srcs_with_flags: A list of SourceWithFlags objects

    Returns:
        A `PlatformParam` struct that contains both platform and non platform
        sources and flags in a way that buck understands. These are either strings,
        or tuples of (source, list of flags that should be used with the corresponding
        source).
    """

    # All path sources and fbcode source references are installed via the
    # `srcs` parameter.
    out_srcs = []
    tp2_dep_srcs = []
    for src in srcs_with_flags:
        if third_party.is_tp2_src_dep(src.src):
            # All third-party sources references are installed via `platform_srcs`
            # so that they're platform aware.
            tp2_dep_srcs.append(src)
        else:
            out_srcs.append(_format_source_with_flags(src))

    out_platform_srcs = (
        src_and_dep_helpers.format_platform_param(
            partial.make(_format_source_with_flags_list_partial, tp2_dep_srcs),
        )
    )

    return src_and_dep_helpers.PlatformParam(out_srcs, out_platform_srcs)

def _normalize_dlopen_enabled(dlopen_enabled):
    """
    Normalizes the dlopen_enabled attribute of cpp rules

    Args:
        dlopen_enabled: Whether the library/binary is dlopen enabled. one of None,
                        True/False, or a dictionary of information for modifying dlopen
                        behavior.

    Returns:
        None, or a dictionary of dlopen_info to be used by cpp rules
    """

    dlopen_info = None

    if dlopen_enabled:
        dlopen_info = {}
        if is_string(dlopen_enabled) or is_unicode(dlopen_enabled):
            dlopen_info["soname"] = dlopen_enabled
        elif is_dict(dlopen_enabled):
            dlopen_info.update(dlopen_enabled)

    return dlopen_info

_IMPLICIT_DEPS = [target_utils.ThirdPartyRuleTarget("libgcc", "atomic")]

_IMPLICIT_PCH_DEPS = []

def _get_implicit_deps(is_precompiled_header):
    """
    Gets the list of `RuleTargets` that should be added as implicit dependencies for cpp rules

    Args:
        is_precompiled_header: Whether we're fetching dependencies for a
                               cpp_precompiled_header rule which has different
                               dependencies.

    Returns:
        A list of `RuleTarget`s that should be added to deps/versioned_deps/platform_deps
    """

    # TODO(#13588666): When using clang with the gcc-5-glibc-2.23 platform,
    # `-latomic` isn't automatically added to the link line, meaning uses
    # of `std::atomic<T>` fail to link with undefined reference errors.
    # So implicitly add this dep here.
    #
    # TODO(#17067102): `cpp_precompiled_header` rules currently don't
    # support `platform_deps` parameter.
    if is_precompiled_header:
        return _IMPLICIT_PCH_DEPS
    else:
        return _IMPLICIT_DEPS

def _get_link_style():
    """
    The link style to use for native binary rules.
    """

    # Initialize the link style using the one set via `gen_modes.py`.
    link_style = config.get_default_link_style()

    # If we're using TSAN, we need to build PIEs, which requires PIC deps.
    # So upgrade to `static_pic` if we're building `static`.
    if sanitizers.get_sanitizer() == "thread" and link_style == "static":
        link_style = "static_pic"

    return link_style

_THIN_LTO_FLAG = ["-flto=thin"]

_LTO_FLAG = ["-flto"]

def _lto_linker_flags_partial(_, compiler):
    if compiler != "clang":
        return []
    if config.get_lto_type() == "thin":
        return _THIN_LTO_FLAG
    return _LTO_FLAG

_SANITIZER_VARIABLE_FORMAT = 'const char* const {name} = "{options}";'

def _sanitizer_config_line(name, default_options, extra_options):
    if extra_options:
        options = dict(default_options)
        options.update(extra_options)
    else:
        options = default_options

    return _SANITIZER_VARIABLE_FORMAT.format(
        name = name,
        options = ":".join([
            "{}={}".format(k, v)
            for k, v in sorted(options.items())
        ]),
    )

_COMMON_INIT_KILL = target_utils.RootRuleTarget("common/init", "kill")

def _get_binary_link_deps(
        base_path,
        name,
        linker_flags = (),
        allocator = "malloc",
        default_deps = True):
    """
    Return a list of dependencies that should apply to *all* binary rules that link C/C++ code.

    This also creates a sanitizer configuration rule if necessary, so this function
    should not be called more than once for a given rule.

    Args:
        base_path: The package path
        name: The name of the rule
        linker_flags: If provided, flags to pass to allocator/converage/sanitizers to
                      make sure proper dependent rules are generated.
        allocator: The allocator to use. This is generally set by a configuration option
                   and retreived in alloctors.bzl
        default_deps: If set, add in a list of "default deps", dependencies that
                      should generally be added to make sure binaries work consistently.
                      e.g. common/init

    Returns:
        A list of `RuleTarget` structs that should be added as dependencies.
    """

    deps = []

    # If we're not using a sanitizer add allocator deps.
    if sanitizers.get_sanitizer() == None:
        deps.extend(allocators.get_allocator_deps(allocator))

    # Add in any dependencies required for sanitizers.
    deps.extend(sanitizers.get_sanitizer_binary_deps())
    deps.append(
        _create_sanitizer_configuration(
            base_path,
            name,
            linker_flags,
        ),
    )

    # Add in any dependencies required for code coverage
    if coverage.get_coverage():
        deps.extend(coverage.get_coverage_binary_deps())

    # We link in our own implementation of `kill` to binaries (S110576).
    if default_deps:
        deps.append(_COMMON_INIT_KILL)

    return deps

# This unfortunately has to be here to get around a circular import in sanitizers.bzl
def _create_sanitizer_configuration(
        base_path,
        name,
        linker_flags = ()):
    """
    Create rules to generate a C/C++ library with sanitizer configuration

    Outputs:
        {name}-san-conf-__generated-lib__: The cxx_library that contains sanitizer
                                           configs

    Args:
        base_path: The base path to the package, used for restricting visibility
        name: The name of the original rule that a sanitizer configuration is being
              created for. Also used when calculating visibility.
        linker_flags: If provided, a list of extra linker flags to add to the
                      generated library

    Returns:
        A `RootRuleTarget` for the generated cxx_library

    """

    sanitizer = sanitizers.get_sanitizer()
    build_mode = _build_mode.get_build_mode_for_base_path(base_path)

    configuration_src = []

    if sanitizer and sanitizer.startswith("address"):
        configuration_src.append(_sanitizer_config_line(
            "kAsanDefaultOptions",
            sanitizers.ASAN_DEFAULT_OPTIONS,
            build_mode.asan_options if build_mode else None,
        ))
        configuration_src.append(_sanitizer_config_line(
            "kUbsanDefaultOptions",
            sanitizers.UBSAN_DEFAULT_OPTIONS,
            build_mode.ubsan_options if build_mode else None,
        ))

        if build_mode and build_mode.lsan_suppressions:
            lsan_suppressions = build_mode.lsan_suppressions
        else:
            lsan_suppressions = sanitizers.LSAN_DEFAULT_SUPPRESSIONS
        configuration_src.append(
            _SANITIZER_VARIABLE_FORMAT.format(
                name = "kLSanDefaultSuppressions",
                options = "\\n".join([
                    "leak:{}".format(l)
                    for l in lsan_suppressions
                ]),
            ),
        )

    if sanitizer and sanitizer == "thread":
        configuration_src.append(_sanitizer_config_line(
            "kTsanDefaultOptions",
            _TSAN_DEFAULT_OPTIONS,
            build_mode.tsan_options if build_mode else None,
        ))

    lib_name = name + "-san-conf-__generated-lib__"

    # Setup a rule to generate the sanitizer configuration C file.
    source_gen_name = name + "-san-conf"

    fb_native.genrule(
        name = source_gen_name,
        visibility = [
            "//{base_path}:{lib_name}".format(base_path = base_path, lib_name = lib_name),
        ],
        out = "san-conf.c",
        cmd = "mkdir -p `dirname $OUT` && echo {0} > $OUT".format(
            shell.quote("\n".join(configuration_src)),
        ),
    )

    # Setup platform default for compilation DB, and direct building.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)

    lib_linker_flags = None
    if linker_flags:
        lib_linker_flags = (
            list(cpp_flags.get_extra_ldflags()) + ["-nodefaultlibs"] + list(linker_flags)
        )

    # Clang does not support fat LTO objects, so we build everything
    # as IR only, and must also link everything with -flto
    platform_linker_flags = None
    if cpp_flags.get_lto_is_enabled():
        platform_linker_flags = src_and_dep_helpers.format_platform_param(
            partial.make(_lto_linker_flags_partial),
        )

    # Setup a rule to compile the sanitizer configuration C file
    # into a library.
    fb_native.cxx_library(
        name = lib_name,
        visibility = [
            "//{base_path}:{name}".format(base_path = base_path, name = name),
        ],
        srcs = [":" + source_gen_name],
        compiler_flags = cpp_flags.get_extra_cflags(),
        linker_flags = lib_linker_flags,
        platform_linker_flags = platform_linker_flags,
        # Use link_whole to make sure the build info symbols are always
        # added to the binary, even if the binary does not refer to them.
        link_whole = True,
        # Use force_static so that the build info symbols are always put
        # directly in the main binary, even if dynamic linking is used.
        force_static = True,
        defaults = {"platform": buck_platform},
        default_platform = buck_platform,
    )

    return target_utils.RootRuleTarget(base_path, lib_name)

cpp_common = struct(
    SOURCE_EXTS = _SOURCE_EXTS,
    SourceWithFlags = _SourceWithFlags,
    assert_linker_flags = _assert_linker_flags,
    assert_preprocessor_flags = _assert_preprocessor_flags,
    create_sanitizer_configuration = _create_sanitizer_configuration,
    default_headers_library = _default_headers_library,
    exclude_from_auto_pch = _exclude_from_auto_pch,
    format_source_with_flags = _format_source_with_flags,
    format_source_with_flags_list = _format_source_with_flags_list,
    get_binary_link_deps = _get_binary_link_deps,
    get_fbcode_default_pch = _get_fbcode_default_pch,
    get_implicit_deps = _get_implicit_deps,
    get_link_style = _get_link_style,
    is_cpp_source = _is_cpp_source,
    normalize_dlopen_enabled = _normalize_dlopen_enabled,
)
