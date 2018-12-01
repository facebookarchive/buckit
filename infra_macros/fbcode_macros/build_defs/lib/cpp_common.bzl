load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@bazel_skylib//lib:partial.bzl", "partial")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:haskell_common.bzl", "haskell_common")
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:auto_headers.bzl", "AutoHeaders", "get_auto_headers")
load("@fbcode_macros//build_defs:auto_pch_blacklist.bzl", "auto_pch_blacklist")
load("@fbcode_macros//build_defs:build_info.bzl", "build_info")
load("@fbcode_macros//build_defs:build_mode.bzl", _build_mode = "build_mode")
load("@fbcode_macros//build_defs:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:cuda.bzl", "cuda")
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs:lex.bzl", "LEX_EXTS", "LEX_LIB", "lex")
load("@fbcode_macros//build_defs:modules.bzl", module_utils = "modules")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:string_macros.bzl", "string_macros")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:yacc.bzl", "YACC_EXTS", "yacc")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool", "read_choice")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_dict", "is_list", "is_string", "is_tuple", "is_unicode")

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

# These header suffixes are used to logically group C/C++ source (e.g.
# `foo/Bar.cpp`) with headers with the following suffixes (e.g. `foo/Bar.h` and
# `foo/Bar-inl.tcc`), such that the source provides all implementation for
# methods/classes declared in the headers.
#
# This is important for a couple reasons:
# 1) Automatic dependencies: Tooling can use this property to automatically
#    manage TARGETS dependencies by extracting `#include` references in sources
#    and looking up the rules which "provide" them.
# 2) Modules: This logical group can be combined into a standalone C/C++ module
#    (when such support is available).
_HEADER_SUFFIXES = (
    ".h",
    ".hpp",
    ".tcc",
    "-inl.h",
    "-inl.hpp",
    "-inl.tcc",
    "-defs.h",
    "-defs.hpp",
    "-defs.tcc",
    "If.h",
    "If.tcc",
    "If-inl.h",
    "If-inl.tcc",
    "Impl.h",
    "Impl.tcc",
    "Impl-inl.h",
    "Impl-inl.tcc",
    "Details.h",
    "Details.tcc",
    "Details-inl.h",
    "Details-inl.tcc",
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

"""
A marker which helps us differentiate between empty/falsey/None values
defaulted in a function's arg list, vs. actually passed in from the caller
with such a value.
"""

_ABSENT_PARAM = struct(_is_absent = True)

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
        src_with_flags: A `SourceWithFlags` object
        platform: If provided, use this to format the source component of
                  `src_with_flags` into a buck label

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

def _format_if(if_func, val, empty, platform, compiler):
    if partial.call(if_func, platform, compiler):
        return val
    return empty

def _modules_enabled_for_platform(platform, compiler):
    return module_utils.enabled_for_platform(platform_utils.to_buck_platform(platform, compiler))

def _format_modules_param(lst):
    return src_and_dep_helpers.format_platform_param(
        partial.make(
            _format_if,
            partial.make(_modules_enabled_for_platform),
            lst,
            [],
        ),
    )

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

    return src_and_dep_helpers.PlatformParam(value = out_srcs, platform_value = out_platform_srcs)

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
    build_mode = _build_mode.get_build_mode_for_current_buildfile()

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
            sanitizers.TSAN_DEFAULT_OPTIONS,
            build_mode.tsan_options if build_mode else None,
        ))

    lib_name = name + "-san-conf-__generated-lib__"

    # Setup a rule to generate the sanitizer configuration C file.
    source_gen_name = name + "-san-conf"

    fb_native.genrule(
        name = source_gen_name,
        labels = ["generated"],
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
        labels = ["generated"],
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

def _convert_contacts(owner, emails):
    """
    Normalize `owner` and `emails` parameters into Buck-style contacts

    Args:
        owners: One of None, a list, or a string of email addresses or handles
        emails: Either None or a list of email address that will also get added to the
                list

    Returns:
        A list of contacts (effectively coalescing owner and emails)
    """
    contacts = []

    if owner != None:
        if is_string(owner):
            contacts.append(owner)
        else:
            contacts.extend(owner)

    if emails != None:
        contacts.extend(emails)

    return contacts

def _split_matching_extensions_and_other(srcs, exts):
    """
    Split a list into two based on the extension of the items.

    Args:
        srcs: A list of source file names
        exts: A collection of extensions to partition on

    Returns:
        A tuple of (<srcs with extensions in `exts`>, <srcs with extensions not in `exts`>)
    """

    matches = []
    leftovers = []

    for src in (srcs or ()):
        _, ext = paths.split_extension(src)
        if ext in exts:
            matches.append(src)
        else:
            leftovers.append(src)

    return (matches, leftovers)

_ASAN_SANITIZER_BINARY_LDFLAGS = [
    "-Wl,--dynamic-list=$(location fbcode//tools/build/buck:asan_dynamic_list.txt)",
]

def _get_sanitizer_binary_ldflags():
    """
    Return any linker flags to use when linking binaries with sanitizer support

    Returns:
        A list of linker flags to use for the configured sanitizer
    """

    sanitizer = sanitizers.get_sanitizer()
    if sanitizer == None:
        fail("Cannot get sanitizer dependencies if sanitizer is disabled")
    if sanitizer.startswith("address"):
        return _ASAN_SANITIZER_BINARY_LDFLAGS
    else:
        return []

_ASAN_SANITIZER_NON_BINARY_DEPS = [
    target_utils.RootRuleTarget("tools/build/sanitizers", "asan-stubs"),
]

def _get_sanitizer_non_binary_deps():
    """
    Return dependencies for library rules for the configured sanitizer / link style

    Returns:
        A list of RootRuleTarget objects
    """

    sanitizer = sanitizers.get_sanitizer()
    if sanitizer == None:
        fail("Cannot get sanitizer dependencies if sanitizer is disabled")

    # We link ASAN weak stub symbols into every DSO so that we don't leave
    # undefined references to *SAN symbols at shared library link time,
    # which allows us to pass `--no-undefined` to the linker to prevent
    # undefined symbols.
    if (sanitizer.startswith("address") and _get_link_style() == "shared"):
        return _ASAN_SANITIZER_NON_BINARY_DEPS
    else:
        return []

def _get_platform_flags_from_arch_flags_partial(platform_flags, platform, _):
    return platform_flags.get(platform)

def _get_platform_flags_from_arch_flags(arch_flags):
    """
    Format a dict of architecture names to flags into a platform flag list
    for Buck.

    Args:
        arch_flags: A dictionary of architecture short names to flags

    Returns:
        A list of tuples of (<buck platform regex>, <list of flags>) where the
        buck platform regexes are architecture appropriate.
    """

    platform_flags = {
        platform: flags
        for arch, flags in sorted(arch_flags.items())
        for platform in platform_utils.get_platforms_for_architecture(arch)
    }

    return src_and_dep_helpers.format_platform_param(
        partial.make(
            _get_platform_flags_from_arch_flags_partial,
            platform_flags,
        ),
    )

def _get_headers_from_sources(srcs):
    """
    Return the headers likely associated with the given sources

    Args:
        srcs: A list of strings representing files or build targets

    Returns:
        A list of header files corresponding to the list of sources. These files are
        validated to exist based on glob()
    """
    split_srcs = [
        paths.split_extension(src)
        for src in srcs
        if "//" not in src and not src.startswith(":")
    ]

    # For e.g. foo.cpp grab a glob on foo.h, foo-inl.h, etc
    return native.glob([
        base + header_ext
        for base, ext in split_srcs
        if ext in _SOURCE_EXTS
        for header_ext in _HEADER_SUFFIXES
    ])

_VALID_STRIP_MODES = ("none", "debug-non-line", "full")

def _get_strip_mode(base_path, name):
    """
    Return a flag to strip debug symbols from binaries.

    Args:
        base_path: The package to check
        name: The name of the rule to check

    Returns:
        One of none, debug-non-line, or full. This depends both on configuration, and
        on the actual rule used (some rules are not stripped for rule-key divergence
        reasons). Note that is "none", not the object None
    """

    # `dev` mode has lightweight binaries, so avoid stripping to keep rule
    # keys stable.
    if config.get_build_mode().startswith("dev"):
        return "none"

    # If this is a core tool, we never strip to keep stable rule keys.
    if core_tools.is_core_tool(base_path, name):
        return "none"

    # Otherwise, read the config setting.
    return read_choice(
        "misc",
        "strip_binaries",
        _VALID_STRIP_MODES,
        default = "none",
    )

_STRIP_LDFLAGS = {
    "full": "-Wl,-S",
    "debug-non-line": "-Wl,--strip-debug-non-line",
    "none": None,
}

def _get_strip_ldflag(mode):
    """ Return the linker flag ot use for the given strip mode """
    return _STRIP_LDFLAGS[mode]

_VALID_SHLIB_INTERFACES = ("disabled", "enabled", "defined_only")

def _read_shlib_interfaces(buck_platform):
    return read_choice(
        "cxx#" + buck_platform,
        "shlib_interfaces",
        _VALID_SHLIB_INTERFACES,
    )

def _get_binary_ldflags(base_path):
    """
    Return ldflags that should be added for binaries via various `.buckconfig` settings.

    Args:
        base_path: The package name
        platform: The fbcode platform

    Returns:
        A list of extra ldflags that should be added.
    """

    ldflags = []

    # If we're using TSAN, we need to build PIEs.
    if sanitizers.get_sanitizer() == "thread":
        ldflags.append("-pie")

    # Remove unused section to reduce the code bloat in sanitizer modes
    if sanitizers.get_sanitizer() != None:
        ldflags.append("-Wl,--gc-sections")

    # It's rare, but some libraries use variables defined in object files
    # in the top-level binary.  This works as, when linking the binary, the
    # linker sees this undefined reference in the dependent shared library
    # and so makes sure to export this symbol definition to the binary's
    # dynamic symbol table.  However, when using shared library interfaces
    # in `defined_only` mode, undefined references are stripped from shared
    # libraries, so the linker never knows to export these symbols to the
    # binary's dynamic symbol table, and the binary fails to load at
    # runtime, as the dynamic loader can't resolve that symbol.
    #
    # So, when linking a binary when using shared library interfaces in
    # `defined_only` mode, pass `--export-dynamic` to the linker to force
    # everything onto the dynamic symbol table.  Since this only affects
    # object files from sources immediately owned by `cpp_binary` rules,
    # this shouldn't have much of a performance issue.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    if (_get_link_style() == "shared" and _read_shlib_interfaces(buck_platform) == "defined_only"):
        ldflags.append("-Wl,--export-dynamic")

    return ldflags

def _get_build_info_linker_flags(
        base_path,
        name,
        rule_type,
        platform,
        compiler):
    """
    Get the linker flags to configure how the linker embeds build info.

    Args:
        base_path: The package name
        name: The rule name
        rule_type: The name of the macro calling this method. Embedded in build info
        platform: The fbcode platform
        compiler: The compiler family (gcc/clang)

    Returns:
        A list of ldflags to add to the build.
    """

    ldflags = []

    mode = build_info.get_build_info_mode(base_path, name)

    # Make sure we're not using non-deterministic build info when caching
    # is enabled.
    if mode == "full" and read_bool("cxx", "cache_links", True):
        fail("cannot use `full` build info when `cxx.cache_links` is set")

    # Add in explicit build info args.
    if mode != "none":
        # Pass the build info mode to the linker.
        ldflags.append("--build-info=" + mode)
        explicit = build_info.get_explicit_build_info(
            base_path,
            name,
            mode,
            rule_type,
            platform,
            compiler,
        )
        ldflags.append("--build-info-build-mode=" + explicit.build_mode)
        if explicit.package_name:
            ldflags.append(
                "--build-info-package-name=" + explicit.package_name,
            )
        if explicit.package_release:
            ldflags.append(
                "--build-info-package-release=" + explicit.package_release,
            )
        if explicit.package_version:
            ldflags.append(
                "--build-info-package-version=" + explicit.package_version,
            )
        ldflags.append("--build-info-compiler=" + explicit.compiler)
        ldflags.append("--build-info-platform=" + explicit.platform)
        ldflags.append("--build-info-rule=" + explicit.rule)
        ldflags.append("--build-info-rule-type=" + explicit.rule_type)

    return ldflags

def _get_ldflags(
        base_path,
        name,
        rule_type,
        binary = False,
        deployable = None,
        strip_mode = None,
        build_info = False,
        lto = False,
        platform = None):
    """
    Gets linker flags that should be applied to native code

    This method grabs linker flags from a number of locations such as:
        - BUILD_MODE files
        - strip modes
        - build info
        - lto configuration
        - the cxx.extra_ldflags configuration arguments

    It can fail if a number of preconditions are not met, but those should have
    straightforward error messages.

    Args:
        base_path: The package of the rule
        name: The name of the rule
        rule_type: The human readable name of the macro/rule. This is used in build info
                   flags and error messages.
        deployable: If True/False, whether this rule outputs a deployable binary.
                    If None, this is determined from the `binary` parameter.
        strip_mode: The strip_mode as returned by _get_strip_mode, or None
                    if it should be determined for the caller.
        build_info: If provided, build info to use in linker flags
        lto: Whether the rule wants to utilize LTO (if lto is supported globally)
        platform: The fbcode platform

    Returns:
        A list of additional linker flags to utilize.
    """

    # Default `deployable` to whatever `binary` was set to, as very rule
    # types make a distinction.
    if deployable == None:
        deployable = binary

    # The `binary`, `build_info`, and `plaform` params only make sense for
    # "deployable" rules.
    if not deployable:
        if binary:
            fail("If binary is set, it must be deployable")
        if lto:
            fail("lto rules must be deployable")
        if build_info:
            fail("build info can only be added to deployable")
    if deployable == (platform == None):
        fail("Deployable rules must have a platform set")

    ldflags = []

    # 1. Add in build-mode ldflags.
    build_mode = _build_mode.get_build_mode_for_current_buildfile()
    if build_mode != None:
        ldflags.extend(build_mode.ld_flags)

    # 2. Add flag to strip debug symbols.
    if strip_mode == None:
        strip_mode = _get_strip_mode(base_path, name)
    strip_ldflag = _get_strip_ldflag(strip_mode)
    if strip_ldflag != None:
        ldflags.append(strip_ldflag)

    # 3. Add in flags specific for linking a binary.
    if binary:
        ldflags.extend(_get_binary_ldflags(base_path))

    # 4. Add in the build info linker flags.
    # In OSS, we don't need to actually use the build info (and the
    # linker will not understand these options anyways) so skip in that case
    if build_info and config.get_use_build_info_linker_flags():
        ldflags.extend(
            _get_build_info_linker_flags(
                base_path,
                name,
                rule_type,
                platform,
                compiler.get_compiler_for_current_buildfile(),
            ),
        )

    # 5. If enabled, add in LTO linker flags.
    if cpp_flags.get_lto_is_enabled():
        global_compiler = config.get_global_compiler_family()
        lto_type = config.get_lto_type()

        compiler.require_global_compiler(
            "can only use LTO in modes with a fixed global compiler",
        )
        if global_compiler == "clang":
            if lto_type not in ("monolithic", "thin"):
                fail("clang does not support {} LTO".format(lto_type))

            # Clang does not support fat LTO objects, so we build everything
            # as IR only, and must also link everything with -flto
            ldflags.append("-flto=thin" if lto_type == "thin" else "-flto")

            # HACK(marksan): don't break HFSort/"Hot Text" (t19644410)
            ldflags.append("-Wl,-plugin-opt,-function-sections")
            ldflags.append("-Wl,-plugin-opt,-profile-guided-section-prefix=false")

            # Equivalent of -fdebug-types-section for LLVM backend
            ldflags.append("-Wl,-plugin-opt,-generate-type-units")
        else:
            if global_compiler != "gcc":
                fail("Invalid global compiler '{}'".format(global_compiler))

            if lto_type != "fat":
                fail("gcc does not support {} LTO".format(cxx_mode.lto_type))

            # GCC has fat LTO objects, where we build everything as both IR
            # and object code and then conditionally opt-in here, at link-
            # time, based on "enable_lto" in the TARGETS file.
            if lto:
                ldflags.extend(cpp_flags.get_gcc_lto_ldflags(base_path, platform))
            else:
                ldflags.append("-fno-lto")

    # 6. Add in command-line ldflags.
    ldflags.extend(cpp_flags.get_extra_ldflags())

    return ldflags

def _cuda_compiler_specific_flags_partial(compiler_specific_flags, has_cuda_srcs, _, compiler):
    return compiler_specific_flags.get("gcc" if has_cuda_srcs else compiler)

# Dependency that contains a standard main that will run folly benchmarks
_FOLLY_BENCHMARK_DEFAULT_MAIN_TARGET = target_utils.RootRuleTarget("common/benchmark", "benchmark_main")

def _convert_cpp(
        name,
        cpp_rule_type,
        buck_rule_type,
        is_library,
        is_buck_binary,
        is_test,
        is_deployable,
        base_module = None,
        module_name = None,
        srcs = [],
        src = None,
        deps = [],
        arch_compiler_flags = {},
        compiler_flags = (),
        known_warnings = [],
        headers = None,
        header_namespace = None,
        compiler_specific_flags = {},
        supports_coverage = None,
        tags = (),
        linker_flags = (),
        arch_preprocessor_flags = {},
        preprocessor_flags = (),
        prefix_header = None,
        precompiled_header = _ABSENT_PARAM,
        propagated_pp_flags = (),
        link_whole = None,
        global_symbols = [],
        allocator = None,
        args = None,
        external_deps = [],
        type = "gtest",
        owner = None,
        emails = None,
        dlopen_enabled = None,
        nodefaultlibs = False,
        shared_system_deps = None,
        system_include_paths = None,
        split_symbols = None,
        env = None,
        use_default_test_main = True,
        use_default_benchmark_main = False,
        lib_name = None,
        nvcc_flags = (),
        hip_flags = (),
        enable_lto = False,
        hs_profile = None,
        dont_link_prerequisites = None,
        lex_args = (),
        yacc_args = (),
        runtime_files = (),
        additional_coverage_targets = (),
        py3_sensitive_deps = (),
        dlls = {},
        versions = None,
        visibility = None,
        auto_headers = None,
        preferred_linkage = None,
        os_deps = None,
        os_linker_flags = None,
        autodeps_keep = False,
        undefined_symbols = False,
        modular_headers = None,
        modules = None,
        overridden_link_style = None,
        rule_specific_deps = None,
        rule_specific_preprocessor_flags = None,
        tests = None):
    base_path = native.package_name()
    visibility = get_visibility(visibility, name)

    if not (is_list(compiler_flags) or is_tuple(compiler_flags)):
        fail(
            "Expected compiler_flags to be a list or a tuple, got {0!r} instead."
                .format(compiler_flags),
        )

    # autodeps_keep is used by dwyu/autodeps and ignored by infra_macros.
    out_srcs = []  # type: List[SourceWithFlags]
    out_headers = []
    out_exported_ldflags = []
    out_ldflags = []
    out_dep_queries = []
    dependencies = []
    os_deps = os_deps or []
    os_linker_flags = os_linker_flags or []
    out_link_style = _get_link_style()
    build_mode = _build_mode.get_build_mode_for_current_buildfile()
    dlopen_info = _normalize_dlopen_enabled(dlopen_enabled)

    # `dlopen_enabled=True` binaries are really libraries.
    is_binary = False if dlopen_info != None else is_deployable
    exported_lang_plat_pp_flags = {}
    platform = (
        platform_utils.get_platform_for_base_path(
            base_path if cpp_rule_type != "cpp_node_extension" else
            # Node rules always use the platforms set in the root PLATFORM
            # file.
            "",
        )
    )
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)

    has_cuda_srcs = cuda.has_cuda_srcs(srcs)

    # TODO(lucian, pbrady, T24109997): this was a temp hack when CUDA doesn't
    # support platform007
    # We still keep it here in case CUDA is lagging on gcc support again;
    # For projects that don't really need CUDA, but depend on CUDA through
    # convenience transitive dependencies, we exclude the CUDA files to
    # unblock migration. Once CUDA supports gcc of the new platform,
    # cuda_deps should be merged back into deps.
    if platform.startswith("platform008"):
        has_cuda_srcs = False
        stripped_attrs = cuda.strip_cuda_properties(
            base_path,
            name,
            compiler_flags,
            preprocessor_flags,
            propagated_pp_flags,
            nvcc_flags,
            arch_compiler_flags,
            arch_preprocessor_flags,
            srcs,
        )
        compiler_flags = stripped_attrs.compiler_flags
        preprocessor_flags = stripped_attrs.preprocessor_flags
        propagated_pp_flags = stripped_attrs.propagated_pp_flags
        nvcc_flags = stripped_attrs.nvcc_flags
        arch_compiler_flags = stripped_attrs.arch_compiler_flags
        arch_preprocessor_flags = stripped_attrs.arch_preprocessor_flags
        srcs = stripped_attrs.srcs
        cuda_srcs = stripped_attrs.cuda_srcs

        if cuda_srcs:
            print("Warning: no CUDA on platform007: rule {}:{} ignoring cuda_srcs: {}"
                .format(base_path, name, cuda_srcs))

    # Figure out whether this rule's headers should be built into a clang
    # module (in supporting build modes).
    out_modular_headers = True

    # Check the global, build mode default.
    global_modular_headers = read_bool("cxx", "modular_headers_default", required = False)
    if global_modular_headers != None:
        out_modular_headers = global_modular_headers

    # Check the build mode file override.
    if (build_mode != None and
        build_mode.cxx_modular_headers != None):
        out_modular_headers = build_mode.cxx_modular_headers

    # Check the rule override.
    if modular_headers != None:
        out_modular_headers = modular_headers

    # Figure out whether this rule should be built using clang modules (in
    # supporting build modes).
    out_modules = True

    # Check the global, build mode default.
    global_modules = read_bool("cxx", "modules_default", required = False)
    if global_modules != None:
        out_modules = global_modules

    # Check the build mode file override.
    if build_mode != None and build_mode.cxx_modules != None:
        out_modules = build_mode.cxx_modules

    # Check the rule override.
    if modules != None:
        out_modules = modules

    # Don't build precompiled headers with modules.
    if cpp_rule_type == "cpp_precompiled_header":
        out_modules = False
    if precompiled_header != _ABSENT_PARAM:
        out_modules = False

    attributes = {
        "name": name,
        "visibility": visibility,
    }

    if tests != None:
        attributes["tests"] = tests

    # Set the base module.
    if base_module != None:
        attributes["base_module"] = base_module

    if module_name != None:
        attributes["module_name"] = module_name

    if is_library:
        if preferred_linkage:
            attributes["preferred_linkage"] = preferred_linkage
        if link_whole:
            attributes["link_whole"] = link_whole
        if global_symbols:
            if platform_utils.get_platform_architecture(
                platform_utils.get_platform_for_base_path(base_path),
            ) == "aarch64":
                # On aarch64 we use bfd linker which doesn't support
                # --export-dynamic-symbol. We force link_whole instead.
                attributes["link_whole"] = True
            else:
                flag = ("undefined" if out_link_style == "static" else "export-dynamic-symbol")
                out_exported_ldflags = [
                    "-Wl,--%s,%s" % (flag, sym)
                    for sym in global_symbols
                ]

    # Parse the `header_namespace` parameter.
    if header_namespace != None:
        header_namespace_whitelist = config.get_header_namespace_whitelist()
        if (base_path, name) not in header_namespace_whitelist and not any([
            # Check base path prefix in header_namespace_whitelist
            len(t) == 1 and base_path.startswith(t[0])
            for t in header_namespace_whitelist
        ]):
            fail((
                "{}(): the `header_namespace` parameter is *not* " +
                "supported in fbcode -- `#include` paths must match " +
                "their fbcode-relative path. ({}/{})"
            ).format(cpp_rule_type, base_path, name))
        out_header_namespace = header_namespace
    else:
        out_header_namespace = base_path

    # Form compiler flags.  We pass everything as language-specific flags
    # so that we can can control the ordering.
    out_lang_plat_compiler_flags = cpp_flags.get_compiler_flags(base_path)
    for lang in cpp_flags.COMPILER_LANGS:
        out_lang_plat_compiler_flags.setdefault(lang, [])
        out_lang_plat_compiler_flags[lang].extend(
            src_and_dep_helpers.format_platform_param(compiler_flags),
        )
        out_lang_plat_compiler_flags[lang].extend(
            src_and_dep_helpers.format_platform_param(
                partial.make(
                    _cuda_compiler_specific_flags_partial,
                    compiler_specific_flags,
                    has_cuda_srcs,
                ),
            ),
        )

    cuda_cpp_output = []
    for flag in nvcc_flags:
        cuda_cpp_output.append("-_NVCC_")
        cuda_cpp_output.append(flag)

    out_lang_plat_compiler_flags.setdefault("cuda_cpp_output", [])
    out_lang_plat_compiler_flags["cuda_cpp_output"].extend(
        src_and_dep_helpers.format_platform_param(cuda_cpp_output),
    )

    out_lang_plat_compiler_flags.setdefault("hip_cpp_output", []).extend(
        src_and_dep_helpers.format_platform_param(hip_flags),
    )

    clang_profile = native.read_config("cxx", "profile")
    if clang_profile != None:
        compiler.require_global_compiler(
            "cxx.profile only supported by modes using clang globally",
            "clang",
        )
        profile_args = [
            "-fprofile-sample-use=$(location {})".format(clang_profile),
            "-fdebug-info-for-profiling",
            # '-fprofile-sample-accurate'
        ]
        out_lang_plat_compiler_flags["c_cpp_output"].extend(
            src_and_dep_helpers.format_platform_param(profile_args),
        )
        out_lang_plat_compiler_flags["cxx_cpp_output"].extend(
            src_and_dep_helpers.format_platform_param(profile_args),
        )

    if out_lang_plat_compiler_flags:
        attributes["lang_platform_compiler_flags"] = (
            out_lang_plat_compiler_flags
        )

    # Form platform-specific compiler flags.
    out_platform_compiler_flags = _get_platform_flags_from_arch_flags(
        arch_compiler_flags,
    )
    if out_platform_compiler_flags:
        attributes["platform_compiler_flags"] = out_platform_compiler_flags

    # Form preprocessor flags.
    out_preprocessor_flags = []
    if not has_cuda_srcs:
        if sanitizers.get_sanitizer() != None:
            out_preprocessor_flags.extend(sanitizers.get_sanitizer_flags())
        out_preprocessor_flags.extend(coverage.get_coverage_flags(base_path))
    _assert_preprocessor_flags(
        "preprocessor_flags",
        preprocessor_flags,
    )
    out_preprocessor_flags.extend(preprocessor_flags)
    if rule_specific_preprocessor_flags != None:
        out_preprocessor_flags.extend(rule_specific_preprocessor_flags)

    # Form language-specific preprocessor flags.
    out_lang_preprocessor_flags = {
        "c": [],
        "cxx": [],
        "assembler_with_cpp": [],
    }
    if build_mode != None:
        if build_mode.aspp_flags:
            out_lang_preprocessor_flags["assembler_with_cpp"].extend(build_mode.aspp_flags)
        if build_mode.cpp_flags:
            out_lang_preprocessor_flags["c"].extend(build_mode.cpp_flags)
        if build_mode.cxxpp_flags:
            out_lang_preprocessor_flags["cxx"].extend(build_mode.cxxpp_flags)
    out_lang_preprocessor_flags["c"].extend(
        cpp_flags.get_extra_cppflags(),
    )
    out_lang_preprocessor_flags["cxx"].extend(
        cpp_flags.get_extra_cxxppflags(),
    )
    out_lang_preprocessor_flags["assembler_with_cpp"].extend(
        cpp_flags.get_extra_cxxppflags(),
    )
    if out_lang_preprocessor_flags:
        attributes["lang_preprocessor_flags"] = out_lang_preprocessor_flags

    # Form platform-specific processor flags.
    out_platform_preprocessor_flags = _get_platform_flags_from_arch_flags(
        arch_preprocessor_flags,
    )
    if out_platform_preprocessor_flags:
        attributes["platform_preprocessor_flags"] = out_platform_preprocessor_flags

    if lib_name != None:
        attributes["soname"] = "lib{}.so".format(lib_name)

    exported_pp_flags = []
    _assert_preprocessor_flags(
        "propagated_pp_flags",
        propagated_pp_flags,
    )
    exported_pp_flags.extend(propagated_pp_flags)
    for path in (system_include_paths or []):
        exported_pp_flags.append("-isystem")
        exported_pp_flags.append(path)
    if exported_pp_flags:
        attributes["exported_preprocessor_flags"] = exported_pp_flags

    # Form platform and language specific processor flags.
    out_lang_plat_pp_flags = {}
    if module_utils.enabled() and out_modules:
        out_lang_plat_pp_flags.setdefault("cxx", [])

        # Add module toolchain flags.
        out_lang_plat_pp_flags["cxx"].extend(
            _format_modules_param(module_utils.get_toolchain_flags()),
        )

        # Tell the compiler that C/C++ sources compiled in this rule are
        # part of the same module as the headers (and so have access to
        # private headers).
        if out_modular_headers:
            module_name = (
                module_utils.get_module_name("fbcode", base_path, name)
            )
            out_lang_plat_pp_flags["cxx"].extend(
                _format_modules_param(["-fmodule-name=" + module_name]),
            )
    if out_lang_plat_pp_flags:
        attributes["lang_platform_preprocessor_flags"] = out_lang_plat_pp_flags

    # Add in the base ldflags.
    out_ldflags.extend(
        _get_ldflags(
            base_path,
            name,
            cpp_rule_type,
            binary = is_binary,
            build_info = is_deployable,
            deployable = is_deployable,
            lto = enable_lto,
            platform = platform if is_deployable else None,
            # Never apply stripping flags to library rules, as they only
            # get linked in `dev` mode which we avoid stripping in anyway,
            # any adding unused linker flags affects rule keys up the tree.
            strip_mode = None if is_deployable else "none",
        ),
    )

    # Add non-binary sanitizer dependencies.
    if (not is_binary and
        sanitizers.get_sanitizer() != None):
        dependencies.extend(_get_sanitizer_non_binary_deps())

    out_ldflags.extend(coverage.get_coverage_ldflags(base_path))

    if is_binary:
        if sanitizers.get_sanitizer() != None:
            out_ldflags.extend(_get_sanitizer_binary_ldflags())
        if (native.read_config("fbcode", "gdb-index") and
            not core_tools.is_core_tool(base_path, name)):
            out_ldflags.append("-Wl,--gdb-index")
        ld_threads = native.read_config("fbcode", "ld-threads")

        # lld does not (yet?) support the --thread-count option, so prevent
        # it from being forwarded when using lld.  bfd seems to be in the
        # same boat, and this happens on aarch64 machines.
        # FIXME: -fuse-ld= may take a path to an lld executable, for which
        #        this check will not work properly. Instead, maybe Context
        #        should have a member named 'linker', as it does with
        #        'compiler'?
        if ld_threads and \
           not core_tools.is_core_tool(base_path, name) and \
           "-fuse-ld=lld" not in out_ldflags and \
           platform_utils.get_platform_architecture(platform_utils.get_platform_for_base_path(base_path)) != \
           "aarch64" and \
           "-fuse-ld=bfd" not in out_ldflags:
            out_ldflags.extend([
                "-Wl,--threads",
                "-Wl,--thread-count," + ld_threads,
            ])

    if nodefaultlibs:
        out_ldflags.append("-nodefaultlibs")

    if emails or owner != None:
        attributes["contacts"] = (
            _convert_contacts(emails = emails, owner = owner)
        )

    if env:
        attributes["env"] = string_macros.convert_env_with_macros(env)

    if args:
        attributes["args"] = string_macros.convert_args_with_macros(args)

    # Handle `dlopen_enabled` binaries.
    if dlopen_info != None:
        # We don't support allocators with dlopen-enabled binaries.
        if allocator != None:
            fail('Cannot use "allocator" parameter with dlopen enabled binaries')

        # We're building a shared lib.
        out_ldflags.append("-shared")

        # If an explicit soname was specified, pass that in.
        soname = dlopen_info.get("soname")
        if soname != None:
            out_ldflags.append("-Wl,-soname=" + soname)

        # Lastly, since we're building a shared lib, use the `static_pic`
        # link style so that PIC is used throughout.
        if out_link_style == "static":
            out_link_style = "static_pic"

    # Add in user-specified linker flags.
    if is_library:
        _assert_linker_flags(linker_flags)

    for flag in linker_flags:
        if flag != "--enable-new-dtags":
            linker_text = string_macros.convert_blob_with_macros(flag, platform = platform)
            if is_binary:
                linker_text = linker_text.replace("$(platform)", buck_platform)
            out_exported_ldflags.extend(["-Xlinker", linker_text])

    # Link non-link-whole libs with `--no-as-needed` to avoid adding
    # unnecessary DT_NEEDED tags during dynamic linking.  Libs marked
    # with `link_whole=True` may contain static intializers, and so
    # need to always generate a DT_NEEDED tag up the transitive link
    # tree. Ignore these arugments on OSX, as the linker doesn't support
    # them
    if (buck_rule_type == "cxx_library" and
        config.get_build_mode().startswith("dev") and
        native.host_info().os.is_linux):
        if link_whole == True:
            out_exported_ldflags.append("-Wl,--no-as-needed")
        else:
            out_exported_ldflags.append("-Wl,--as-needed")

    # Generate rules to handle lex sources.
    lex_srcs, srcs = _split_matching_extensions_and_other(srcs, LEX_EXTS)
    for lex_src in lex_srcs:
        header, source = lex(name, lex_args, lex_src, platform, visibility)
        out_headers.append(header)
        out_srcs.append(_SourceWithFlags(target_utils.RootRuleTarget(base_path, source[1:]), ["-w"]))

    # Generate rules to handle yacc sources.
    yacc_srcs, srcs = _split_matching_extensions_and_other(
        srcs,
        YACC_EXTS,
    )
    for yacc_src in yacc_srcs:
        yacc_headers, source = yacc(
            name,
            yacc_args,
            yacc_src,
            platform,
            visibility,
        )
        out_headers.extend(yacc_headers)
        out_srcs.append(_SourceWithFlags(target_utils.RootRuleTarget(base_path, source[1:]), None))

    # Convert and add in any explicitly mentioned headers into our output
    # headers.
    if is_list(headers) or is_tuple(headers):
        out_headers.extend(
            src_and_dep_helpers.convert_source_list(base_path, headers),
        )
        # TODO(pjameson): hasattr is for old python code calling with dictionary-like things.

    elif is_dict(headers) or hasattr(headers, "items"):
        converted = {
            k: src_and_dep_helpers.convert_source(base_path, v)
            for k, v in headers.items()
        }

        if is_list(out_headers) or is_tuple(out_headers):
            out_headers = {k: k for k in out_headers}

        out_headers.update(converted)

    # x in automatically inferred headers.
    auto_headers = get_auto_headers(auto_headers)
    if auto_headers == AutoHeaders.SOURCES:
        src_headers = sets.make(_get_headers_from_sources(srcs))
        src_headers = sets.to_list(sets.difference(src_headers, sets.make(out_headers)))

        # Looks simple, right? But if a header is explicitly added in, say, a
        # dictionary mapping, we want to make sure to keep the original mapping
        # and drop the F -> F mapping
        if is_list(out_headers):
            out_headers.extend(sorted(src_headers))
        else:
            # Let it throw AttributeError if update() can't be found neither
            out_headers.update({k: k for k in src_headers})

    # Convert the `srcs` parameter.  If `known_warnings` is set, add in
    # flags to mute errors.
    for src in srcs:
        src = src_and_dep_helpers.parse_source(base_path, src)
        flags = None
        if (known_warnings == True or
            (known_warnings and
             src_and_dep_helpers.get_parsed_source_name(src) in known_warnings)):
            flags = ["-Wno-error"]
        out_srcs.append(_SourceWithFlags(src = src, flags = flags))

    formatted_srcs = _format_source_with_flags_list(out_srcs)
    if cpp_rule_type != "cpp_precompiled_header":
        attributes["srcs"] = formatted_srcs.value
        attributes["platform_srcs"] = formatted_srcs.platform_value
    else:
        attributes["srcs"] = src_and_dep_helpers.without_platforms(formatted_srcs)

    for lib in (shared_system_deps or []):
        out_exported_ldflags.append("-l" + lib)

    # We don't support symbols splitting, but we can at least strip the
    # debug symbols entirely (as some builds rely on the actual binary not
    # being bloated with debug info).
    if split_symbols:
        out_ldflags.append("-Wl,-S")

    # Handle DLL deps.
    if dlls:
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        dll_deps, dll_ldflags, dll_dep_queries = (
            haskell_common.convert_dlls(
                name,
                platform,
                buck_platform,
                dlls,
                visibility,
            )
        )
        dependencies.extend(dll_deps)
        out_ldflags.extend(dll_ldflags)
        if not dont_link_prerequisites:
            out_dep_queries.extend(dll_dep_queries)

        # We don't currently support dynamic linking with DLL support, as
        # we don't have a great way to prevent dependency DSOs needed by
        # the DLL, but *not* needed by the top-level binary, from being
        # dropped from the `DT_NEEDED` tags when linking with
        # `--as-needed`.
        if out_link_style == "shared":
            out_link_style = "static_pic"

    # Some libraries need to opt-out of linker errors about undefined
    # symbols.
    if (is_library and
        # TODO(T23121628): The way we build shared libs in non-ASAN
        # sanitizer modes leaves undefined references to *SAN symbols.
        (sanitizers.get_sanitizer() == None or
         sanitizers.get_sanitizer().startswith("address")) and
        # TODO(T23121628): Building python binaries with omnibus causes
        # undefined references in preloaded libraries, so detect this
        # via the link-style and ignore for now.
        config.get_default_link_style() == "shared" and
        not undefined_symbols):
        out_ldflags.append("-Wl,--no-undefined")

    # Get any linker flags for the current OS
    for os_short_name, flags in os_linker_flags:
        if os_short_name == config.get_current_os():
            out_exported_ldflags.extend(flags)

    # Set the linker flags parameters.
    if buck_rule_type == "cxx_library":
        attributes["exported_linker_flags"] = out_exported_ldflags
        attributes["linker_flags"] = out_ldflags
    else:
        attributes["linker_flags"] = out_exported_ldflags + out_ldflags

    attributes["labels"] = list(tags)

    if use_default_benchmark_main:
        dependencies.append(_FOLLY_BENCHMARK_DEFAULT_MAIN_TARGET)

    if is_test:
        attributes["labels"].extend(label_utils.convert_labels(platform, "c++"))
        if coverage.is_coverage_enabled(base_path):
            attributes["labels"].append("coverage")
        attributes["use_default_test_main"] = use_default_test_main
        if "serialize" in tags:
            attributes["run_test_separately"] = True

        # C/C++ gtest tests implicitly depend on gtest/gmock libs, and by
        # default on our custom main
        if type == "gtest":
            gtest_deps = [
                d.strip()
                for d in config.get_gtest_lib_dependencies()
            ]
            if use_default_test_main:
                main_test_dep = config.get_gtest_main_dependency()
                if main_test_dep:
                    gtest_deps.append(main_test_dep)
            dependencies.extend(
                [target_utils.parse_target(dep) for dep in gtest_deps],
            )
        else:
            attributes["framework"] = type

    allocator = allocators.normalize_allocator(allocator)

    # C/C++ Lua main modules get statically linked into a special extension
    # module.
    if cpp_rule_type == "cpp_lua_main_module":
        attributes["preferred_linkage"] = "static"

    # For binaries, set the link style.
    if is_buck_binary:
        attributes["link_style"] = overridden_link_style or out_link_style

    # Translate runtime files into resources.
    if runtime_files:
        attributes["resources"] = runtime_files

    # Translate additional coverage targets.
    if additional_coverage_targets:
        attributes["additional_coverage_targets"] = additional_coverage_targets

    # Convert three things here:
    # - Translate dependencies.
    # - Add and translate py3 sensitive deps
    # -  Grab OS specific dependencies and add them to the normal
    #    list of dependencies. We bypass buck's platform support because it
    #    requires us to parse a bunch of extra files we know we won't use,
    #    and because it's just a little fragile
    current_os = config.get_current_os()
    for dep in deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))
    for dep in py3_sensitive_deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))
    for os, _deps in os_deps:
        if os == current_os:
            for dep in _deps:
                dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))

    # If we include any lex sources, implicitly add a dep on the lex lib.
    if lex_srcs:
        dependencies.append(LEX_LIB)

    # Add in binary-specific link deps.
    if is_binary:
        dependencies.extend(
            _get_binary_link_deps(
                base_path,
                name,
                attributes["linker_flags"],
                allocator = allocator,
                default_deps = not nodefaultlibs,
            ),
        )

    if rule_specific_deps != None:
        dependencies.extend(rule_specific_deps)

    # Add external deps.
    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

    # Add in any CUDA deps.  We only add this if it's not always present,
    # it's common to explicitly depend on the cuda runtime.
    if has_cuda_srcs and not cuda.has_cuda_dep(dependencies):
        # TODO: If this won't work, should it just fail?
        print(("Warning: rule {}:{} with .cu files has to specify CUDA " +
               "external_dep to work.").format(base_path, name))

    # Set the build platform, via both the `default_platform` parameter and
    # the default flavors support.
    if cpp_rule_type != "cpp_precompiled_header":
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        attributes["default_platform"] = buck_platform
        if not is_deployable:
            attributes["defaults"] = {"platform": buck_platform}

    # Add in implicit deps.
    if not nodefaultlibs:
        dependencies.extend(
            _get_implicit_deps(
                cpp_rule_type == "cpp_precompiled_header",
            ),
        )

    # Add implicit toolchain module deps.
    if module_utils.enabled() and out_modules:
        dependencies.extend(
            map(target_utils.parse_target, module_utils.get_implicit_module_deps()),
        )

    # Modularize libraries.
    if module_utils.enabled() and is_library and out_modular_headers:
        exported_lang_plat_pp_flags.setdefault("cxx", [])

        # If we're using modules, we need to add in the `module.modulemap`
        # file and make sure it gets installed at the root of the include
        # tree so that clang can locate it for auto-loading.  To do this,
        # we need to clear the header namespace (which defaults to the base
        # path) and instead propagate its value via the keys of the header
        # dict so that we can make sure it's only applied to the user-
        # provided headers and not the module map.
        if is_list(out_headers) or is_tuple(out_headers):
            out_headers = {
                paths.join(out_header_namespace, src_and_dep_helpers.get_source_name(h)): h
                for h in out_headers
            }
        else:
            out_headers = {
                paths.join(out_header_namespace, h): s
                for h, s in out_headers.items()
            }
        out_header_namespace = ""

        # Create rule to generate the implicit `module.modulemap`.
        module_name = module_utils.get_module_name("fbcode", base_path, name)
        mmap_name = name + "-module-map"
        module_utils.module_map_rule(
            mmap_name,
            module_name,
            # There are a few header suffixes (e.g. '-inl.h') that indicate a
            # "private" extension to some library interface. We generally want
            # to keep these are non modular. So mark them private/textual.
            {
                h: ["private", "textual"] if h.endswith(("-inl.h", "-impl.h", "-pre.h", "-post.h")) else []
                for h in out_headers
            },
            labels = ["generated"],
        )

        # Add in module map.
        out_headers["module.modulemap"] = ":" + mmap_name

        # Create module compilation rule.
        mod_name = name + "-module"
        module_flags = []
        module_flags.extend(out_preprocessor_flags)
        module_flags.extend(out_lang_preprocessor_flags["cxx"])
        module_flags.extend(exported_pp_flags)

        # Build each module header in it's own context.
        module_flags.extend(["-Xclang", "-fmodules-local-submodule-visibility"])

        # TODO(T36925825): Set `FOLLY_XLOG_STRIP_PREFIXES` for module
        # compilations, so that folly's xlog logging library can properly
        # reconstruct path names from mangled `__FILE__` values.
        module_flags.append("-DFOLLY_XLOG_STRIP_PREFIXES=FB_BUCK_MODULE_HOME")

        module_platform_flags = []
        module_platform_flags.extend(exported_lang_plat_pp_flags["cxx"])
        module_platform_flags.extend(out_platform_preprocessor_flags)
        module_platform_flags.extend(
            out_lang_plat_compiler_flags["cxx_cpp_output"],
        )
        module_platform_flags.extend(out_platform_compiler_flags)
        module_deps, module_platform_deps = (
            src_and_dep_helpers.format_all_deps(dependencies)
        )
        module_utils.gen_module(
            mod_name,
            module_name,
            # TODO(T32915747): Due to a clang bug when using module and
            # header maps together, clang cannot update the module at load
            # time with the correct path to it's new home location (modules
            # are originally built in the sandbox of a Buck `genrule`, but
            # are used from a different location: Buck's header symlink
            # trees.  To work around this, we add support for manually
            # fixing up the embedded module home location to be the header
            # symlink tree.
            override_module_home = (
                "{}/{}/{}#header-mode-symlink-tree-with-header-map,headers%s"
                    .format(common_paths.get_gen_path(), base_path, name)
            ),
            headers = out_headers,
            flags = module_flags,
            platform_flags = module_platform_flags,
            default_platform = buck_platform,
            deps = module_deps,
            platform_deps = module_platform_deps,
            labels = ["generated"],
        )

        # Expose module via C++ preprocessor flags.
        exported_lang_plat_pp_flags["cxx"].extend(
            _format_modules_param(
                ["-fmodule-file={}=$(location :{})"
                    .format(module_name, mod_name)],
            ),
        )

    # TODO(T36925825): Set `FOLLY_XLOG_STRIP_PREFIXES` for non-module
    # compilations.  We don't put anything useful here, but as xlog.h is built
    # with this set, it then expects to find it set in all downstream users.
    if module_utils.enabled():
        out_preprocessor_flags.append('-DFOLLY_XLOG_STRIP_PREFIXES=""')

    # Write out preprocessor flags.
    if out_preprocessor_flags:
        attributes["preprocessor_flags"] = out_preprocessor_flags

    # Write out prefix header.
    if prefix_header:
        attributes["prefix_header"] = prefix_header

    # Write out our output headers.
    if out_headers:
        if buck_rule_type == "cxx_library":
            attributes["exported_headers"] = out_headers
        else:
            attributes["headers"] = out_headers

    # Set an explicit header namespace if not the default.
    if out_header_namespace != base_path:
        attributes["header_namespace"] = out_header_namespace

    if exported_lang_plat_pp_flags:
        attributes["exported_lang_platform_preprocessor_flags"] = exported_lang_plat_pp_flags

    # If any deps were specified, add them to the output attrs.  For
    # libraries, we always use make these exported, since this is the
    # expected behavior in fbcode.
    if dependencies:
        src_and_dep_helpers.restrict_repos(dependencies)
        deps_param, plat_deps_param = (
            ("exported_deps", "exported_platform_deps") if is_library else ("deps", "platform_deps")
        )
        out_deps, out_plat_deps = src_and_dep_helpers.format_all_deps(dependencies)
        attributes[deps_param] = out_deps
        if out_plat_deps:
            attributes[plat_deps_param] = out_plat_deps

    if out_dep_queries:
        attributes["deps_query"] = " union ".join(out_dep_queries)
        attributes["link_deps_query_whole"] = True

    # fbconfig supports a `cpp_benchmark` rule which we convert to a
    # `cxx_binary`.  Just make sure we strip options that `cxx_binary`
    # doesn't support.
    if buck_rule_type == "cxx_binary":
        attributes.pop("args", None)
        attributes.pop("contacts", None)

    # (cpp|cxx)_precompiled_header rules take a 'src' attribute (not
    # 'srcs', drop that one which was stored above).  Requires a deps list.
    if buck_rule_type == "cxx_precompiled_header":
        attributes["src"] = src
        exclude_names = [
            "lang_platform_compiler_flags",
            "lang_preprocessor_flags",
            "linker_flags",
            "preprocessor_flags",
            "srcs",
        ]
        for exclude_name in exclude_names:
            if exclude_name in attributes:
                attributes.pop(exclude_name)
        if "deps" not in attributes:
            attributes["deps"] = []

    # Should we use a default PCH for this C++ lib / binary?
    # Only applies to certain rule types.
    if cpp_rule_type in (
        "cpp_library",
        "cpp_binary",
        "cpp_unittest",
        "cxx_library",
        "cxx_binary",
        "cxx_test",
    ):
        # Was completely left out in the rule? (vs. None to disable autoPCH)
        if precompiled_header == _ABSENT_PARAM:
            precompiled_header = _get_fbcode_default_pch(out_srcs, base_path, name)

    if precompiled_header != _ABSENT_PARAM and precompiled_header:
        attributes["precompiled_header"] = precompiled_header

    if is_binary and versions != None:
        attributes["version_universe"] = (
            third_party.get_version_universe(versions.items())
        )

    return attributes

cpp_common = struct(
    ABSENT_PARAM = _ABSENT_PARAM,
    SOURCE_EXTS = _SOURCE_EXTS,
    SourceWithFlags = _SourceWithFlags,
    assert_linker_flags = _assert_linker_flags,
    assert_preprocessor_flags = _assert_preprocessor_flags,
    convert_contacts = _convert_contacts,
    convert_cpp = _convert_cpp,
    create_sanitizer_configuration = _create_sanitizer_configuration,
    default_headers_library = _default_headers_library,
    exclude_from_auto_pch = _exclude_from_auto_pch,
    format_source_with_flags = _format_source_with_flags,
    format_source_with_flags_list = _format_source_with_flags_list,
    get_binary_ldflags = _get_binary_ldflags,
    get_binary_link_deps = _get_binary_link_deps,
    get_build_info_linker_flags = _get_build_info_linker_flags,
    get_fbcode_default_pch = _get_fbcode_default_pch,
    get_headers_from_sources = _get_headers_from_sources,
    get_implicit_deps = _get_implicit_deps,
    get_ldflags = _get_ldflags,
    get_link_style = _get_link_style,
    get_platform_flags_from_arch_flags = _get_platform_flags_from_arch_flags,
    get_sanitizer_binary_ldflags = _get_sanitizer_binary_ldflags,
    get_sanitizer_non_binary_deps = _get_sanitizer_non_binary_deps,
    get_strip_ldflag = _get_strip_ldflag,
    get_strip_mode = _get_strip_mode,
    is_cpp_source = _is_cpp_source,
    normalize_dlopen_enabled = _normalize_dlopen_enabled,
    split_matching_extensions_and_other = _split_matching_extensions_and_other,
)
