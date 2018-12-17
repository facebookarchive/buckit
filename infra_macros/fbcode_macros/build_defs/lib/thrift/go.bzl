"""
"""

load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def _go_package_name(
        go_thrift_namespaces,
        go_pkg_base_path,
        base_path,
        thrift_src):
    thrift_namespaces = go_thrift_namespaces or {}
    thrift_file = paths.basename(thrift_src)

    namespace = thrift_namespaces.get(thrift_file)
    if namespace != None:
        return namespace.replace(".", "/")

    if go_pkg_base_path != None:
        base_path = go_pkg_base_path
    return paths.join(base_path, paths.split_extension(thrift_file)[0])

def _get_lang():
    return "go"

def _get_names():
    return ("go",)

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        go_thrift_namespaces = None,
        go_pkg_base_path = None,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = options
    thrift_prefix = _go_package_name(
        go_thrift_namespaces,
        go_pkg_base_path,
        base_path,
        thrift_src,
    )

    genfiles = [
        "ttypes.go",
        "constants.go",
    ] + [
        "{}.go".format(service.lower())
        for service in services
    ]

    gen_paths = [paths.join(thrift_prefix, gf) for gf in genfiles]
    return {path: paths.join("gen-go", path) for path in gen_paths}

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        go_pkg_base_path = None,
        go_thrift_namespaces = None,
        go_thrift_src_inter_deps = {},
        visibility = None,
        **_kwargs):
    _ignore = thrift_srcs
    _ignore = options
    export_deps = sets.make(deps)
    for thrift_src, sources in sources_map.items():
        pkg = _go_package_name(
            go_thrift_namespaces,
            go_pkg_base_path,
            base_path,
            thrift_src,
        )
        thrift_noext = paths.split_extension(
            paths.basename(thrift_src),
        )[0]

        rule_name = "{}-{}".format(name, paths.basename(pkg))
        sets.insert(export_deps, ":{}".format(rule_name))

        out_deps = []
        out_deps.extend(deps)
        out_deps.append("//thrift/lib/go/thrift:thrift")

        if thrift_noext in go_thrift_src_inter_deps:
            for local_dep in go_thrift_src_inter_deps[thrift_noext]:
                local_dep_name = ":{}-{}".format(name, local_dep)
                out_deps.append(local_dep_name)
                sets.insert(export_deps, local_dep_name)

        fb_native.go_library(
            name = rule_name,
            labels = ["generated"],
            visibility = visibility,
            srcs = sources.values(),
            package_name = pkg,
            deps = out_deps,
        )

    # Generate a parent package with exported deps of the each thrift_src.
    # Since this package has no go source files and is never used directly
    # the name doesn't matter and it only needs to be unique.
    pkg_name = paths.join(
        base_path,
        # generate unique package name to avoid pkg name clash
        "{}-__generated{}".format(name, hash(name)),
    )

    fb_native.go_library(
        name = name,
        visibility = visibility,
        srcs = [],
        package_name = pkg_name,
        exported_deps = sets.to_list(export_deps),
    )

def _get_options(base_path, parsed_options):
    _ignored = (base_path,)
    opts = {
        "thrift_import": "thrift/lib/go/thrift",
    }
    opts.update(parsed_options)
    return opts

go_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_names = _get_names,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
    get_options = _get_options,
)
