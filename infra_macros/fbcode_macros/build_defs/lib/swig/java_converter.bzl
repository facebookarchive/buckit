"""
Specializer to support generating Java libraries from swig sources.
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
    return "java"

def _get_lang_opt():
    return "-java"

def _get_lang_flags(java_package = None, **kwargs):
    _ignore = kwargs
    flags = []

    # Forward the user-provided `java_package` parameter.
    if java_package != None:
        flags.append("-package")
        flags.append(java_package)

    return flags

def _get_generated_sources(module):
    _ignore = module
    return {"": "."}

def _get_language_rule(
        base_path,
        name,
        module,
        hdr,
        src,
        gen_srcs,
        cpp_deps,
        deps,
        java_library_name = None,
        visibility = None,
        **kwargs):
    # Build the C/C++ Java extension from the generated C/C++ sources.
    ext_name = name + "-ext"

    # Setup platform default for compilation DB, and direct building.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    ext_deps, ext_platform_deps = (
        src_and_dep_helpers.format_all_deps(
            cpp_deps + [target_utils.RootRuleTarget("common/java/jvm", "jvm")],
        )
    )

    fb_native.cxx_library(
        name = ext_name,
        visibility = get_visibility(visibility, ext_name),
        srcs = [src],
        # Swig-generated code breaks strict-aliasing with gcc
        # (http://www.swig.org/Doc3.0/SWIGDocumentation.html#Java_compiling_dynamic).
        compiler_flags = ["-fno-strict-aliasing"],
        soname = (
            "lib{}.so".format(
                module if java_library_name == None else java_library_name,
            )
        ),
        link_style = kwargs.get("java_link_style"),
        deps = ext_deps,
        platform_deps = ext_platform_deps,
        # When using e.g. %feature("director") in Something.i, SWIG includes
        # "Something.h" in the source code of the C/C++ Java extension.
        headers = [hdr],
        header_namespace = "",
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
    )

    # Pack all generated source directories into a source zip, which we'll
    # feed into the Java library rule.
    src_zip_name = name + ".src.zip"
    fb_native.zip_file(
        name = src_zip_name,
        visibility = get_visibility(visibility, src_zip_name),
        # Java rules are C/C++ platform agnostic, so we're forced to choose a
        # fixed platform at parse-time (which means Java binaries will only
        # ever build against one platform at a time).
        srcs = (
            [
                "{}#{}".format(s, platform_utils.get_buck_platform_for_base_path(base_path))
                for s in gen_srcs.values()
            ]
        ),
        out = src_zip_name,
    )

    # Generate the wrapping Java library.
    out_deps = []
    out_deps.extend(deps)
    out_deps.append(":" + name + "-ext")
    fb_native.java_library(
        name = name,
        visibility = get_visibility(visibility, name),
        srcs = [":" + src_zip_name],
        deps = out_deps,
    )

    return []

java_converter = LangConverterInfo(
    get_lang = _get_lang,
    get_lang_opt = _get_lang_opt,
    get_lang_flags = _get_lang_flags,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
