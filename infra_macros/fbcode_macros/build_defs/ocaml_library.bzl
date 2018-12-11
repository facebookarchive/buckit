load("@fbcode_macros//build_defs/lib:ocaml_common.bzl", "ocaml_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def ocaml_library(
        name,
        srcs = (),
        deps = (),
        compiler_flags = None,
        ocamldep_flags = None,
        native = True,
        warnings_flags = None,
        supports_coverage = None,
        external_deps = (),
        visibility = None,
        ppx_flag = None,
        nodefaultlibs = False):
    attrs = ocaml_common.convert_ocaml(
        name,
        "ocaml_library",
        srcs = srcs,
        deps = deps,
        compiler_flags = compiler_flags,
        ocamldep_flags = ocamldep_flags,
        native = native,
        warnings_flags = warnings_flags,
        supports_coverage = supports_coverage,
        external_deps = external_deps,
        visibility = visibility,
        ppx_flag = ppx_flag,
        nodefaultlibs = nodefaultlibs,
    )
    fb_native.ocaml_library(**attrs)
