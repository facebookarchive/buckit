load("@fbcode_macros//build_defs/lib:core_tools.bzl", "core_tools")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_choice", "read_int")

def _create_build_info(
        build_mode,
        buck_package,
        name,
        rule_type,
        platform,
        epochtime = 0,
        host = "",
        package_name = "",
        package_version = "",
        package_release = "",
        path = "",
        revision = "",
        revision_epochtime = 0,
        time = "",
        time_iso8601 = "",
        upstream_revision = "",
        upstream_revision_epochtime = 0,
        user = ""):
    # when adding a new entry in the struct below, make sure to add its key to
    # _BUILD_INFO_KEYS
    return struct(
        build_mode = build_mode,
        compiler = compiler.get_compiler_for_current_buildfile(),
        epochtime = epochtime,
        host = host,
        package_name = package_name,
        package_release = package_release,
        package_version = package_version,
        path = path,
        platform = platform,
        revision = revision,
        revision_epochtime = revision_epochtime,
        rule = "fbcode:" + buck_package + ":" + name,
        rule_type = rule_type,
        time = time,
        time_iso8601 = time_iso8601,
        upstream_revision = upstream_revision,
        upstream_revision_epochtime = upstream_revision_epochtime,
        user = user,
    )

def _get_build_info(package_name, name, rule_type, platform):
    """
    Gets a build_info struct from various configurations (or default values)

    This struct has values passed in by the packaging system in order to
    stamp things like the build epoch, platform, etc into the final binary.

    This returns stable values by default so that non-release builds do not
    affect rulekeys.

    Args:
        package_name: The name of the package that contains the build rule
                      that needs build info. No leading slashes
        name: The name of the rule that needs build info
        rule_type: The type of rule that is being built. This should be the
                   macro name, not the underlying rule type. (e.g. cpp_binary,
                   not cxx_binary)
        platform: The platform that is being built for
    """
    build_mode = config.get_build_mode()
    if core_tools.is_core_tool(package_name, name):
        return _create_build_info(
            build_mode,
            package_name,
            name,
            rule_type,
            platform,
        )
    else:
        return _create_build_info(
            build_mode,
            package_name,
            name,
            rule_type,
            platform,
            package_name = native.read_config("build_info", "package_name", ""),
            epochtime = read_int("build_info", "epochtime", 0),
            host = native.read_config("build_info", "host", ""),
            package_release = native.read_config("build_info", "package_release", ""),
            package_version = native.read_config("build_info", "package_version", ""),
            path = native.read_config("build_info", "path", ""),
            revision = native.read_config("build_info", "revision", ""),
            revision_epochtime = read_int("build_info", "revision_epochtime", 0),
            time = native.read_config("build_info", "time", ""),
            time_iso8601 = native.read_config("build_info", "time_iso8601", ""),
            upstream_revision = native.read_config("build_info", "upstream_revision", ""),
            upstream_revision_epochtime = read_int("build_info", "upstream_revision_epochtime", 0),
            user = native.read_config("build_info", "user", ""),
        )

# Build info settings which affect rule keys.
_ExplicitBuildInfo = provider(fields = [
    "build_mode",
    "compiler",
    "package_name",
    "package_release",
    "package_version",
    "platform",
    "rule",
    "rule_type",
])

_VALID_BUILD_INFO_MODES = ("full", "stable", "none")

def _get_build_info_mode(base_path, name):
    """
    Return the build info style to use for the given rule.
    """

    # Make sure we're not using full build info when building core tools,
    # otherwise we could introduce nondeterminism in rule keys.
    if core_tools.is_core_tool(base_path, name):
        return "stable"
    return read_choice("fbcode", "build_info", _VALID_BUILD_INFO_MODES, default = "none")

def _get_explicit_build_info(base_path, name, mode, rule_type, platform, compiler):
    """
    Return the build info which can/should affect rule keys (causing rebuilds
    if it changes), and is passed into rules via rule-key-affecting parameters.
    This is contrast to "implicit" build info, which must not affect rule keys
    (e.g. build time, build user), to avoid spurious rebuilds.

    Args:
        base_path: The package of the rule. Used in metadata
        name: The name of the rule. Used in metadata
        mode: The mode as returned from `get_build_info_mode`
        rule_type: The type of the rule/macro, used as metadata for build info
        platform: The fbcode platform
        compiler: The compiler used (e.g. gcc, clang)

    Returns:
        A `ExplicitBuildInfo` struct
    """

    if mode not in ("full", "stable"):
        fail("Build mode must be one of 'full' or 'stable'")

    # We consider package build info explicit, as we must re-build binaries if
    # it changes, regardless of whether nothing else had changed (e.g.
    # T22942388).
    #
    # However, we whitelist core tools and never set this explicitly, to avoid
    # transitively trashing rule keys.
    package_name = None
    package_version = None
    package_release = None
    if mode == "full" and not core_tools.is_core_tool(base_path, name):
        package_name = native.read_config("build_info", "package_name")
        package_version = native.read_config("build_info", "package_version")
        package_release = native.read_config("build_info", "package_release")

    return _ExplicitBuildInfo(
        package_name = package_name,
        build_mode = config.get_build_mode(),
        compiler = compiler,
        package_release = package_release,
        package_version = package_version,
        platform = platform,
        rule = "fbcode:{}:{}".format(base_path, name),
        rule_type = rule_type,
    )

# These keys should be kept in sync with struct returned from get_build_info
# method.
_BUILD_INFO_KEYS = (
    "build_mode",
    "compiler",
    "epochtime",
    "host",
    "package_name",
    "package_release",
    "package_version",
    "path",
    "platform",
    "revision_epochtime",
    "revision",
    "rule_type",
    "rule",
    "time_iso8601",
    "time",
    "upstream_revision_epochtime",
    "upstream_revision",
    "user",
)

build_info = struct(
    get_build_info = _get_build_info,
    get_build_info_mode = _get_build_info_mode,
    get_explicit_build_info = _get_explicit_build_info,
    BUILD_INFO_KEYS = _BUILD_INFO_KEYS,
)
