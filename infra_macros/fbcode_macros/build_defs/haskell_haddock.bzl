load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def haskell_haddock(
        name,
        deps = (),
        haddock_flags = (),
        visibility = None):
    base_path = native.package_name()
    attrs = {}
    if haddock_flags:
        attrs["haddock_flags"] = haddock_flags

    out_deps = [
        src_and_dep_helpers.convert_build_target(base_path, target)
        for target in deps
    ]

    fb_native.haskell_haddock(
        name = name,
        visibility = get_visibility(visibility, name),
        platform = platform_utils.get_buck_platform_for_base_path(base_path),
        deps = out_deps,
        **attrs
    )
