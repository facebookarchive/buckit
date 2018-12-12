"""
Specializer to support generating Go libraries from swig sources.
"""

load("@fbcode_macros//build_defs/lib/swig:lang_converter_info.bzl", "LangConverterInfo")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load(
    "@fbsource//tools/build_defs:fb_native_wrapper.bzl",
    "fb_native",
)

def _get_lang():
    return "go"

def _get_lang_opt():
    return "-go"

def _get_lang_flags(go_package_name = None, **kwargs):
    _ignore = kwargs
    return [
        "-cgo",
        "-intgosize",
        "64",  # should fit most of the cases
        "-module",
        go_package_name,
    ]

def _get_generated_sources(module):
    src = module + ".go"
    return {src: src}

def _get_language_rule(
        base_path,
        name,
        module,
        hdr,
        src,
        gen_srcs,
        cpp_deps,
        deps,
        go_package_name = None,
        visibility = None,
        **kwargs):
    _ignore = module
    _ignore = hdr
    _ignore = kwargs

    # create wrapper cxx_library rule that includes generated .cc files
    for dep in cpp_deps:
        deps.extend(src_and_dep_helpers.format_deps([target_utils.RuleTarget(
            name = "{}-ext".format(dep.name),
            base_path = dep.base_path,
            repo = dep.repo,
        )]))
        fb_native.cxx_library(
            name = "{}-ext".format(dep.name),
            deps = src_and_dep_helpers.format_deps([dep]),
            srcs = [src],
        )

    # generate the cgo_library
    fb_native.cgo_library(
        name = name,
        package_name = go_package_name,
        visibility = get_visibility(visibility, name),
        # platform is required for cxx_genrule (copied from java)
        srcs = (
            [
                "{}#{}".format(s, platform_utils.get_buck_platform_for_base_path(base_path))
                for s in gen_srcs.values()
            ]
        ),
        deps = deps,
    )

    return []

go_converter = LangConverterInfo(
    get_lang = _get_lang,
    get_lang_opt = _get_lang_opt,
    get_lang_flags = _get_lang_flags,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
