"""
Specializer to support generating OCaml libraries from thrift sources.
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_THRIFT_OCAML_LIBS = [
    target_utils.RootRuleTarget("common/ocaml/thrift", "thrift"),
]

_THRIFT_OCAML_DEPS = [
    target_utils.RootRuleTarget("hphp/hack/src/third-party/core", "core"),
]

def _get_lang():
    return "ocaml2"

def _get_names():
    return ("ocaml2",)

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = options

    thrift_base = paths.split_extension(paths.basename(thrift_src))[0]
    thrift_base = thrift_common.capitalize_only(thrift_base)

    genfiles = []

    genfiles.append("%s_consts.ml" % thrift_base)
    genfiles.append("%s_types.ml" % thrift_base)
    for service in services:
        service = thrift_common.capitalize_only(service)
        genfiles.append("%s.ml" % service)

    return {path: path for path in genfiles}

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **_kwargs):
    _ignore = thrift_srcs
    _ignore = options

    dependencies = []
    dependencies.extend(_THRIFT_OCAML_DEPS)
    dependencies.extend(_THRIFT_OCAML_LIBS)
    for dep in deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))

    fb_native.ocaml_library(
        name = name,
        visibility = get_visibility(visibility, name),
        srcs = thrift_common.merge_sources_map(sources_map).values(),
        deps = (src_and_dep_helpers.format_all_deps(dependencies))[0],
    )

def _get_compiler():
    return config.get_thrift_ocaml_compiler()

def _get_compiler_args(
        compiler_lang,
        flags,
        options,
        **_kwargs):
    """
    Return compiler args when compiling for ocaml.
    """
    _ignore = compiler_lang

    args = []

    # The OCaml compiler relies on the HS2 compiler to parse .thrift sources to JSON
    args.append("-c")
    args.append("$(exe {})".format(config.get_thrift_hs2_compiler()))

    # Format the options and pass them into the ocaml compiler.
    for option, val in options.items():
        flag = "--" + option
        if val != None:
            flag += "=" + val
        args.append(flag)

    # Include rule-specific flags.
    args.extend(flags)

    return args

ocaml_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_names = _get_names,
    get_compiler = _get_compiler,
    get_compiler_args = _get_compiler_args,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
