load("@fbcode_macros//build_defs/lib:rust_common.bzl", "rust_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def rust_unittest(
        name,
        srcs = None,
        deps = None,
        external_deps = None,
        features = None,
        rustc_flags = None,
        crate = None,
        crate_root = None,
        framework = True,
        preferred_linkage = None,
        proc_macro = False,
        visibility = None,
        licenses = None):
    attrs = rust_common.convert_rust(
        name,
        "rust_unittest",
        srcs = srcs,
        deps = deps,
        external_deps = external_deps,
        features = features,
        rustc_flags = rustc_flags,
        crate = crate,
        crate_root = crate_root,
        framework = framework,
        preferred_linkage = preferred_linkage,
        proc_macro = proc_macro,
        visibility = visibility,
        licenses = licenses,
    )
    fb_native.rust_test(**attrs)
