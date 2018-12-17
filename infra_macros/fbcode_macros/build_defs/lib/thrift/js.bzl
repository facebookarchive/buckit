"""
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def _get_lang():
    return "js"

def _get_names():
    return ("js",)

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **_kwargs):
    _ignore = base_path
    _ignore = name

    thrift_base = paths.split_extension(paths.basename(thrift_src))[0]

    genfiles = []
    genfiles.append("%s_types.js" % thrift_base)
    for service in services:
        genfiles.append("%s.js" % service)

    out_dir = "gen-nodejs" if "node" in options else "gen-js"
    return {
        paths.join("node_modules", thrift_base, path): paths.join(out_dir, path)
        for path in genfiles
    }

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility = None,
        **_kwargs):
    _ignore = base_path
    _ignore = thrift_srcs
    _ignore = options

    sources = thrift_common.merge_sources_map(sources_map)

    cmds = []

    for dep in deps:
        cmds.append('rsync -a $(location {})/ "$OUT"'.format(dep))

    for dst, raw_src in sources.items():
        src = src_and_dep_helpers.get_source_name(raw_src)
        dst = paths.join('"$OUT"', dst)
        cmds.append("mkdir -p {}".format(paths.dirname(dst)))
        cmds.append("cp {} {}".format(paths.basename(src), dst))

    fb_native.genrule(
        name = name,
        visibility = visibility,
        out = common_paths.CURRENT_DIRECTORY,
        labels = ["generated"],
        srcs = sources.values(),
        cmd = " && ".join(cmds),
    )

js_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_names = _get_names,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
