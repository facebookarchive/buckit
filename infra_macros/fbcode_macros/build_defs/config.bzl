# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
User configurable settings for the buck macro library

NOTE: Many of these settings will be gradually factored out into just the
      macro files that require them (e.g. thrift settings)
"""

load(
    "@fbcode_macros//build_defs/config:read_configs.bzl", "read_boolean",
    "read_list", "read_string", "read_facebook_internal_string"
)


def _get_add_auto_headers_glob():
    """
    Determines whether to add an autoheaders dependency.

    This should not be used outside of the Facebook codebase, as it breaks
    assumptions about cross package file ownership

    Returns:
        Whether or not to add an autoheaders dependency
    """
    return read_boolean("fbcode", "add_auto_headers_glob", False)


def _get_allocators():
    """
    Get the targets used for various types of allocators
    """
    return {
        "jemalloc":
        read_list(
            "fbcode", "allocators.jemalloc", ["jemalloc//jemalloc:jemalloc"],
            delimiter=","),
        "jemalloc_debug":
        read_list(
            "fbcode", "allocators.jemalloc_debug",
            ["jemalloc//jemalloc:jemalloc_debug"],
            delimiter=","),
        "tcmalloc":
        read_list(
            "fbcode", "allocators.tcmalloc", ["tcmalloc//tcmalloc:tcmalloc"],
            delimiter=","),
        "malloc":
        read_list(
            "fbcode", "allocators.malloc", [],
            delimiter=","),
    }


def _get_auto_pch_blacklist():
    """
    Gets directories that should not have precopmied headers

    If provided, a list of directories that should be opted out of automatically
    receiving precompiled headers when pch is enabled

    Returns:
        A list of directories that should not receive precompiled headers
    """
    return read_list("fbcode", "auto_pch_blacklist", [], delimiter=",")


def _get_build_mode():
    """
    Gets the name of the build mode.

    This affects some compiler flags that are added as well as other build
    settings

    Returns:
        The build mode
    """
    return read_string("fbcode", "build_mode", "dev")


def _get_compiler_family():
    """
    The family of compiler that is in use.

    If not set, it will be determined from the name of the cxx.compiler binary

    Returns:
        Either "clang" or "gcc" depending on settings
    """
    family = read_string("fbcode", "compiler_family", None)
    if not family:
        cxx = read_config("cxx", "cxx", "gcc")
        family = "clang" if "clang" in cxx else "gcc"
    return family


def _get_core_tools_path():
    """
    Get the path to a list of core tools

    If set, the include_def style path to a file that contains a list of core
    tools. This is only useful in Facebook\'s repository and is used to reduce
    rulekey thrashing

    Returns:
        The path to a list of core tools, or "" if not set
    """
    return read_string("fbcode", "core_tools_path", "")


def _get_coverage():
    """
    Whether to gather coverage information or not
    """
    return read_boolean("fbcode", "coverage", False)


def _get_current_host_os():
    """ Get a string version of the host os. This will eventually go away """
    overridden_os = read_string("fbcode", "os_family", None)
    if overridden_os != None:
        if overridden_os in ["linux", "mac", "windows"]:
            return overridden_os
        fail("Could not determine a supported os from config. Got %r" % overridden_os)

    info = native.host_info()
    if info.os.is_linux:
        return "linux"
    elif info.os.is_macos:
        return "mac"
    elif info.os.is_windows:
        return "windows"
    fail("Could not determine a supported os. Got %r" % info)


def _get_current_repo_name():
    """
    Gets a name for the current repository from configuration

    For rules of the form @/repo:path:rule, if repo equals this value, the rule
    is assumed to be underneath the root cell, rather than a third party
    dependency. This should not be used outside of Facebook

    NOTE: This will soon be deprecated

    Returns:
        The name of the current repo
    """
    return read_string("fbcode", "current_repo_name", "fbcode")


def _get_cython_compiler():
    """
    The target that will provide cython compiler
    """
    return read_string("cython", "cython_compiler", None)


def _get_default_allocator():
    """
    Which allocator to use when not specified explicitly

    Returns:
        The allocator from fbcode.allocators that should be used by default
    """
    return read_string("fbcode", "default_allocator", "malloc")


def _get_default_link_style():
    """
    The default link style to use

    This can be modified for different languages as necessary

    Returns:
        One of "static", "shared" or "any"
    """
    return read_string("defaults.cxx_library", "type", "static")


def _get_fbcode_style_deps():
    """
    Whether or not dependencies are fbcode-style dependencies

    If true, use fbcode style rules, if false, use buck style ones.
    fbcode style rules must begin with @/, and do not support cells.
    Buck style rules are exactly like those on buckbuild.com. This must be
    consistent for an entire cell
    NOTE: Most of this logic has been deprecated

    Returns:
        Whether or not to use fbcode style deps
    """
    return read_boolean("fbcode", "fbcode_style_deps", False)


def _get_fbcode_style_deps_are_third_party():
    """
    Whether rules starting with "@/" should be treated like third-party rules

    If enabled, rules starting with "@/" should be converted to third-party
    libraries that use the first component of the path as the cell name

    NOTE: This will be deprecated in the future

    Returns:
        Whether to convert @/ rules to third-party dependencies
    """
    return read_boolean("fbcode", "fbcode_style_deps_are_third_party", True)


def _get_forbid_raw_buck_rules():
    """
    Whether to forbid raw buck rules that are not in whitelisted_raw_buck_rules
    """
    return read_boolean("fbcode", "forbid_raw_buck_rules", False)


def _get_gtest_lib_dependencies():
    """
    The targets that will provide gtest C++ tests\' gtest and gmock deps
    """
    return read_string("fbcode", "gtest_lib_dependencies", None)


def _get_gtest_main_dependency():
    """
    The target that will provide gtest C++ tests\' main function
    """
    return read_string("fbcode", "gtest_main_dependency", None)


def _get_header_namespace_whitelist():
    """
    List of targets that are allowed to use header_namespace in cpp_* rules

    Returns:
        A list of tuples of basepath and rule that are allowed to use
          header_namespace
    """
    return [
        tuple(target.split(":", 1))
        for target in read_list("fbcode", "header_namespace_whitelist", [], ",")
    ]


def _get_lto_type():
    """
    What kind of Link Time Optimization the compiler supports
    """
    return read_string("fbcode", "lto_type", None)


def _get_pyfi_overrides_path():
    """
    If set, use PyFI overrides for python external_deps from this file
    """
    return read_string("python", "pyfi_overrides_path", None)


def _get_python_typing_config_tool():
    """
    If set, use this tool to generate typing information for python-typecheck
    """
    return read_string("python", "typing_config", None)


def _get_require_platform():
    """
    If true, require that fbcode.platform is specified
    """
    return read_boolean("fbcode", "require_platform", False)


def _get_sanitizer():
    """
    The type of sanitizer to try to use. If not set, do not use it
    """
    return read_string("fbcode", "sanitizer", None)


def _get_third_party_buck_directory():
    """
    An additional dirctory that is added to all third party paths in a monorepo
    """
    return read_string("fbcode", "third_party_buck_directory", "")


def _get_third_party_config_path():
    """
    The path to a file that contains a third-party config to be loaded

    The path should be a root relative file that contains a third-party config
    that will be loaded. If not provided, a default one is created

    NOTE: This will likely be deprecated and replaced in shipit

    Returns:
        The path to include
    """
    return read_string("fbcode", "third_party_config_path", "")


def _get_third_party_use_build_subdir():
    """
    Whether to assume that there is a "build" subdirectory in the third-party dir

    Returns:
        True if "build" is a subdirectory of third-party, and should be used for
        third party dependencies, else False
    """
    return read_boolean("fbcode", "third_party_use_build_subdir", False)


def _get_third_party_use_platform_subdir():
    """
    Whether $fbcode.platform exists in the third-party directory

    More specifically,  the third-party directory has a first level subdirectory
    for the platform specified by fbcode.platform

    Returns:
        True if there exists a platform directory underneath the third-party
        directory that should be used, else False
    """
    return read_boolean("fbcode", "third_party_use_platform_subdir", False)


def _get_third_party_use_tools_subdir():
    """
    Whether there is a tools subdirectory in third-party that should be used

    Whether to assume that there is a "tools" subdirectory in the third-party dir
    that should be used for things like compilers and various utilities

    Returns:
        True if "tools" is a subdirectory of third-party, and should be used for
        third party dependencies, else False
    """
    return read_boolean("fbcode", "third_party_use_tools_subdir", False)


def _get_thrift_compiler():
    """
    The target for the top level cpp thrift compiler
    """
    return read_string("thrift", "compiler", "thrift//thrift/compiler:thrift")


def _get_thrift2_compiler():
    """
    The target for the cpp2 thrift compiler
    """
    return read_string(
        "thrift", "compiler2", "thrift//thrift/compiler/py:thrift"
    )


def _get_thrift_deprecated_apache_compiler():
    """
    The target for the apache thrift compiler
    """
    return read_facebook_internal_string("thrift", "deprecated_apache_compiler", "")


def _get_thrift_hs2_compiler():
    """
    The target for the haskell thrift compiler
    """
    return read_facebook_internal_string("thrift", "hs2_compiler", "")


def _get_thrift_ocaml_compiler():
    """
    The target for the OCaml thrift compiler
    """
    return read_facebook_internal_string("thrift", "ocaml_compiler", "")


def _get_thrift_swift_compiler():
    """
    The target for the swift thrift compiler
    """
    return read_facebook_internal_string("thrift", "swift_compiler", "")


def _get_thrift_templates():
    """
    The target that generates thrift templates
    """
    return read_string(
        "thrift", "templates", "thrift//thrift/compiler/generate:templates"
    )


def _get_unknown_cells_are_third_party():
    """
    Whether unspecified cells should be considered third-party ones

    More specifically, whether or not cells that are not in the [repositories]
    section should instead be assumed to be in the third-party directory, and
    folly the directory structure that fbcode uses

    Returns:
        Whether unknown cells should be considered third-party dependencies
    """
    return read_boolean("fbcode", "unknown_cells_are_third_party", False)


def _get_use_build_info_linker_flags():
    """
    Whether or not to provide the linker with build_info flags.

    These arguments go to a custom linker script at Facebook, and should not be
    used outside of Facebook

    Returns:
        Whether or not to use extra linker flags
    """
    return read_boolean("fbcode", "use_build_info_linker_flags", False)


def _get_use_custom_par_args():
    """
    If set, use custom build arguments for Facebook\'s internal pex build script
    """
    return read_boolean("fbcode", "use_custom_par_args", False)


def _get_whitelisted_raw_buck_rules():
    """
    A list of rules that are allowed to use each type of raw buck rule.

    This is a list of buck rule types to path:target that should be allowed to
    use raw buck rules. e.g. cxx_library=watchman:headers

    Returns:
        dictionary of rule type to list of tuples of base path / rule name
    """
    whitelisted_raw_buck_rules_str = read_string(
        "fbcode", "whitelisted_raw_buck_rules", ""
    )
    whitelisted_raw_buck_rules = {}
    for rule_group in whitelisted_raw_buck_rules_str.strip().split(","):
        if not rule_group:
            continue
        rule_type, rule = rule_group.strip().split("=", 1)
        if rule_type not in whitelisted_raw_buck_rules:
            whitelisted_raw_buck_rules[rule_type] = []
        whitelisted_raw_buck_rules[rule_type].append(tuple(rule.split(":", 1)))
    return whitelisted_raw_buck_rules


config = struct(
    get_add_auto_headers_glob=_get_add_auto_headers_glob,
    get_allocators=_get_allocators,
    get_auto_pch_blacklist=_get_auto_pch_blacklist,
    get_build_mode=_get_build_mode,
    get_compiler_family=_get_compiler_family,
    get_core_tools_path=_get_core_tools_path,
    get_coverage=_get_coverage,
    get_current_os=_get_current_host_os,
    get_current_repo_name=_get_current_repo_name,
    get_cython_compiler=_get_cython_compiler,
    get_default_allocator=_get_default_allocator,
    get_default_link_style=_get_default_link_style,
    get_fbcode_style_deps=_get_fbcode_style_deps,
    get_fbcode_style_deps_are_third_party=_get_fbcode_style_deps_are_third_party,
    get_forbid_raw_buck_rules=_get_forbid_raw_buck_rules,
    get_gtest_lib_dependencies=_get_gtest_lib_dependencies,
    get_gtest_main_dependency=_get_gtest_main_dependency,
    get_header_namespace_whitelist=_get_header_namespace_whitelist,
    get_lto_type=_get_lto_type,
    get_pyfi_overrides_path=_get_pyfi_overrides_path,
    get_python_typing_config_tool=_get_python_typing_config_tool,
    get_require_platform=_get_require_platform,
    get_sanitizer=_get_sanitizer,
    get_third_party_buck_directory=_get_third_party_buck_directory,
    get_third_party_config_path=_get_third_party_config_path,
    get_third_party_use_build_subdir=_get_third_party_use_build_subdir,
    get_third_party_use_platform_subdir=_get_third_party_use_platform_subdir,
    get_third_party_use_tools_subdir=_get_third_party_use_tools_subdir,
    get_thrift2_compiler=_get_thrift2_compiler,
    get_thrift_deprecated_apache_compiler=_get_thrift_deprecated_apache_compiler,
    get_thrift_compiler=_get_thrift_compiler,
    get_thrift_hs2_compiler=_get_thrift_hs2_compiler,
    get_thrift_ocaml_compiler=_get_thrift_ocaml_compiler,
    get_thrift_swift_compiler=_get_thrift_swift_compiler,
    get_thrift_templates=_get_thrift_templates,
    get_unknown_cells_are_third_party=_get_unknown_cells_are_third_party,
    get_use_build_info_linker_flags=_get_use_build_info_linker_flags,
    get_use_custom_par_args=_get_use_custom_par_args,
    get_whitelisted_raw_buck_rules=_get_whitelisted_raw_buck_rules,
)
