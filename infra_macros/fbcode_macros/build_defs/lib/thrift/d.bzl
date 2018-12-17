load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def _get_lang():
    return "d"

def _get_names():
    return ("d",)

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        d_thrift_namespaces = None,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = options
    thrift_base = paths.split_extension(paths.basename(thrift_src))[0]
    thrift_namespaces = d_thrift_namespaces or {}
    thrift_prefix = thrift_namespaces.get(thrift_src, "").replace(".", "/")

    genfiles = []

    genfiles.append("%s_types.d" % thrift_base)
    genfiles.append("%s_constants.d" % thrift_base)

    for service in services:
        genfiles.append("%s.d" % service)

    gen_paths = [paths.join(thrift_prefix, genfile) for genfile in genfiles]
    return {path: paths.join("gen-d", path) for path in gen_paths}

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **_kwargs):
    _ignore = base_path
    _ignore = thrift_srcs
    _ignore = options
    sources = thrift_common.merge_sources_map(sources_map)
    fb_native.d_library(
        name = name,
        visibility = visibility,
        srcs = sources,
        deps = deps + ["//thrift/lib/d:thrift"],
    )

d_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_names = _get_names,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
