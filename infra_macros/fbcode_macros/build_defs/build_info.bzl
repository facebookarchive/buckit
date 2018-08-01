load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_int")
load("@fbcode_macros//build_defs:core_tools.bzl", "core_tools")

def _create_build_info(
    build_mode,
    buck_package,
    name,
    rule_type,
    platform,
    epochtime=0,
    host="",
    package_name="",
    package_version="",
    package_release="",
    path="",
    revision="",
    revision_epochtime=0,
    time="",
    time_iso8601="",
    upstream_revision="",
    upstream_revision_epochtime=0,
    user="",
):
    return struct(
        build_mode=build_mode,
        rule="fbcode:" + buck_package + ":" + name,
        platform=platform,
        rule_type=rule_type,
        epochtime=epochtime,
        host=host,
        package_name=package_name,
        package_version=package_version,
        package_release=package_release,
        path=path,
        revision=revision,
        revision_epochtime=revision_epochtime,
        time=time,
        time_iso8601=time_iso8601,
        upstream_revision=upstream_revision,
        upstream_revision_epochtime=upstream_revision_epochtime,
        user=user,
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
    if core_tools.is_core_tool(package_name,name):
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
            epochtime=read_int("build_info", "epochtime", 0),
            host=read_config("build_info", "host", ""),
            package_name=read_config("build_info", "package_name", ""),
            package_version=read_config("build_info", "package_version", ""),
            package_release=read_config("build_info", "package_release", ""),
            path=read_config("build_info", "path", ""),
            revision=read_config("build_info", "revision", ""),
            revision_epochtime=read_int("build_info", "revision_epochtime", 0),
            time=read_config("build_info", "time", ""),
            time_iso8601=read_config("build_info", "time_iso8601", ""),
            upstream_revision=read_config("build_info", "upstream_revision", ""),
            upstream_revision_epochtime=read_int("build_info", "upstream_revision_epochtime", 0),
            user=read_config("build_info", "user", ""),
        )

build_info = struct(
    get_build_info = _get_build_info,
)
