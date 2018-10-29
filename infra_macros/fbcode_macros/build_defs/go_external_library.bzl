load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")

def go_external_library(
        name,
        library,
        package_name = None,
        deps = (),
        exported_deps = None,
        licenses = (),
        visibility = None):
    """
    Wrapper around prebuilt_go_library

    Args:
        name: The name of the rule
        library: The path to the library's prebuilt artifact
        package_name: The name of the go package
        deps: A list of non-exported dependencies
        exported_deps: A list of exported dependencies
        licenses: A list of license files that apply to this library
        visibility: The visibility for this rule. It may be modified by global settings
    """
    visibility = get_visibility(visibility, name)
    package = native.package_name()

    if exported_deps:
        exported_deps = [
            src_and_dep_helpers.convert_build_target(package, d)
            for d in exported_deps
        ]
    deps = [
        src_and_dep_helpers.convert_build_target(package, target)
        for target in deps
    ]

    fb_native.prebuilt_go_library(
        name = name,
        library = library,
        package_name = package_name,
        licenses = licenses,
        visibility = visibility,
        exported_deps = exported_deps,
        deps = deps,
    )
