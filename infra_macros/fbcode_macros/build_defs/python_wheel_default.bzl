load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load(
    "@fbcode_macros//build_defs/lib:python_typing.bzl",
    "gen_typing_config",
    "get_typing_config_target",
)
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def _wheel_override_version_check(name, platform_versions):
    wheel_platform = native.read_config("python", "wheel_platform_override")
    if wheel_platform:
        wheel_platform = "py3-{}".format(wheel_platform)
        building_platform = "py3-{}".format(
            platform_utils.get_platform_for_current_buildfile(),
        )

        # Setting defaults to "foo" and "bar" so that they're different in case both return None
        if platform_versions.get(building_platform, "foo") != platform_versions.get(
            wheel_platform,
            "bar",
        ):
            print(
                ("We're showing this warning because you're building for {0} " +
                 "and the default version of {4} for this platform ({2}) " +
                 "doesn't match the default version for {1} ({3}). " +
                 "The resulting binary might not work on {0}. " +
                 "Make sure there is a {0} wheel for {3} version of {4}.").format(
                    wheel_platform,
                    building_platform,
                    platform_versions.get(wheel_platform, "None"),
                    platform_versions.get(building_platform, "None"),
                    name,
                ),
            )

def _wrap_text(text, width = 79):
    """
    Splits the text into lines at most `width` in width and returns their list.

    Note that unlike textwrap.wrap this function does not try to split at word
    boundaries and simply takes chunks the text into chunks of size `width`.
    """
    lines, chunk = [], 0
    for _ in range(len(text)):
        if chunk >= len(text):
            break
        lines.append(text[chunk:chunk + width])
        chunk += width
    return lines

def _error_rules(name, msg, visibility = None):
    """
    Return rules which generate an error with the given message at build
    time.
    """

    msg = "ERROR: " + msg
    msg = "\n".join(_wrap_text(msg))

    genrule_name = "{}-gen".format(name)
    fb_native.cxx_genrule(
        name = genrule_name,
        visibility = get_visibility(visibility, genrule_name),
        out = "out.cpp",
        cmd = "echo {} 1>&2; false".format(shell.quote(msg)),
    )

    fb_native.cxx_library(
        name = name,
        srcs = [":{}-gen".format(name)],
        exported_headers = [":{}-gen".format(name)],
        visibility = ["PUBLIC"],
    )

def python_wheel_default(platform_versions, visibility = None):
    name = paths.basename(native.package_name())

    _wheel_override_version_check(name, platform_versions)

    # If there is no default for either py2 or py3 for the given platform
    # Then we should fail to return a rule, instead of silently building
    # but not actually providing the wheel.  To do this, emit and add
    # platform deps onto "error" rules that will fail at build time.
    platform_versions = dict(platform_versions)
    for platform in platform_utils.get_platforms_for_host_architecture():
        py2_plat = platform_utils.get_buck_python_platform(platform, major_version = 2)
        py3_plat = platform_utils.get_buck_python_platform(platform, major_version = 3)
        present_for_any_python_version = (
            py2_plat in platform_versions or py3_plat in platform_versions
        )
        if not present_for_any_python_version:
            msg = (
                '{}: wheel does not exist for platform "{}"'
                    .format(name, platform)
            )
            error_name = "{}-{}-error".format(name, platform)
            _error_rules(error_name, msg)
            platform_versions[py2_plat] = error_name
            platform_versions[py3_plat] = error_name

    # TODO: Figure out how to handle typing info from wheels
    if get_typing_config_target():
        gen_typing_config(name, visibility = visibility)
    fb_native.python_library(
        name = name,
        visibility = visibility,
        platform_deps = [
            ("{}$".format(platform_utils.escape(py_platform)), [":" + version])
            for py_platform, version in sorted(platform_versions.items())
        ],
    )
