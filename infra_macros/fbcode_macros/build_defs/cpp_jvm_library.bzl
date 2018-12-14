load("@bazel_skylib//lib:partial.bzl", "partial")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_FORMATTER_ARCHS = {"x86_64": "amd64"}

def _formatter_partial(flags, platform):
    # Remap arch to JVM-specific names.
    arch = platform.target_arch
    arch = _FORMATTER_ARCHS.get(arch, arch)
    return [flag.format(arch = arch, platform = platform.alias) for flag in flags]

def cpp_jvm_library(name, major_version, visibility = None):
    platform_jvm_path = "/usr/local/fb-jdk-{}-{{platform}}".format(major_version)
    jvm_path = "/usr/local/fb-jdk-{}".format(major_version)

    fb_native.cxx_library(
        name = name,
        visibility = get_visibility(visibility, name),
        # We use include/library paths to wrap the custom FB JDK installed at
        # system locations.  As such, we don't properly hash various components
        # (e.g. headers, libraries) pulled into the build.  Longer-term, we
        # should move the FB JDK into tp2 to do this properly.
        exported_platform_preprocessor_flags = (
            src_and_dep_helpers.format_platform_param(
                partial.make(
                    _formatter_partial,
                    [
                        "-isystem",
                        paths.join(platform_jvm_path, "include"),
                        "-isystem",
                        paths.join(platform_jvm_path, "include", "linux"),
                        "-isystem",
                        paths.join(jvm_path, "include"),
                        "-isystem",
                        paths.join(jvm_path, "include", "linux"),
                    ],
                ),
            )
        ),
        exported_platform_linker_flags = (
            src_and_dep_helpers.format_platform_param(
                partial.make(
                    _formatter_partial,
                    [
                        "-L{}/jre/lib/{{arch}}/server".format(platform_jvm_path),
                        "-Wl,-rpath={}/jre/lib/{{arch}}/server".format(platform_jvm_path),
                        "-L{}/jre/lib/{{arch}}/server".format(jvm_path),
                        "-Wl,-rpath={}/jre/lib/{{arch}}/server".format(jvm_path),
                        "-ljvm",
                    ],
                ),
            )
        ),
    )
