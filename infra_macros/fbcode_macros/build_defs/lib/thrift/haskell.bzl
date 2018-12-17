"""
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:haskell_common.bzl", "haskell_common")
load("@fbcode_macros//build_defs/lib:haskell_rules.bzl", "haskell_rules")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_THRIFT_HS_LIBS = [
    target_utils.RootRuleTarget("thrift/lib/hs", "thrift"),
    target_utils.RootRuleTarget("thrift/lib/hs", "types"),
    target_utils.RootRuleTarget("thrift/lib/hs", "protocol"),
    target_utils.RootRuleTarget("thrift/lib/hs", "transport"),
]

_THRIFT_HS_LIBS_DEPRECATED = [
    target_utils.RootRuleTarget("thrift/lib/hs", "hs"),
]

_THRIFT_HS2_LIBS = [
    target_utils.RootRuleTarget("common/hs/thrift/lib", "codegen-types-only"),
    target_utils.RootRuleTarget("common/hs/thrift/lib", "protocol"),
]

_THRIFT_HS2_SERVICE_LIBS = [
    target_utils.RootRuleTarget("common/hs/thrift/lib", "channel"),
    target_utils.RootRuleTarget("common/hs/thrift/lib", "codegen"),
    target_utils.RootRuleTarget("common/hs/thrift/lib", "processor"),
    target_utils.RootRuleTarget("common/hs/thrift/lib", "types"),
    target_utils.RootRuleTarget("common/hs/thrift/lib/if", "application-exception-hs2"),
]

_THRIFT_HS_PACKAGES = [
    "base",
    "bytestring",
    "containers",
    "deepseq",
    "hashable",
    "QuickCheck",
    "text",
    "unordered-containers",
    "vector",
]

_THRIFT_HS2_PACKAGES = [
    "aeson",
    "base",
    "binary-parsers",
    "bytestring",
    "containers",
    "data-default",
    "deepseq",
    "hashable",
    "STMonadTrans",
    "text",
    "transformers",
    "unordered-containers",
    "vector",
]

def _get_extra_includes(hs_includes = (), **_kwargs):
    return hs_includes

def _deprecated_get_lang():
    return "hs"

def _hs2_get_lang():
    return "hs2"

def _deprecated_get_compiler():
    return config.get_thrift_compiler()

def _hs2_get_compiler():
    return config.get_thrift_hs2_compiler()

def _hs2_get_compiler_args(
        compiler_lang,
        flags,
        options,
        hs_required_symbols = None,
        **_kwargs):
    _ignore = compiler_lang

    args = ["--hs"]

    # Format the options and pass them into the hs2 compiler.
    for option, val in options.items():
        flag = "--" + option
        if val != None:
            flag += "=" + val
        args.append(flag)

    # Include rule-specific flags.
    args.extend(flags)

    # Add in the require symbols parameter.
    if hs_required_symbols != None:
        args.append("--required-symbols")
        args.append(hs_required_symbols)

    return args

def _deprecated_get_names():
    return ("hs",)

def _hs2_get_names():
    return ("hs2",)

def _deprecated_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        hs_namespace = None,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = options

    thrift_base = paths.split_extension(paths.basename(thrift_src))[0]
    thrift_base = thrift_common.capitalize_only(thrift_base)
    namespace = hs_namespace or ""

    genfiles = []

    genfiles.append("%s_Consts.hs" % thrift_base)
    genfiles.append("%s_Types.hs" % thrift_base)
    for service in services:
        service = thrift_common.capitalize_only(service)
        genfiles.append("%s.hs" % service)
        genfiles.append("%s_Client.hs" % service)
        genfiles.append("%s_Iface.hs" % service)
        genfiles.append("%s_Fuzzer.hs" % service)
    namespace = namespace.replace(".", "/")

    gen_paths = [paths.join(namespace, genfile) for genfile in genfiles]
    return {path: paths.join("gen-hs", path) for path in gen_paths}

def _camel(s):
    return "".join([w[0].upper() + w[1:] for w in s.split("_") if w != ""])

def _hs2_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        hs_namespace = None,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = options

    thrift_base = paths.split_extension(paths.basename(thrift_src))[0]
    thrift_base = thrift_common.capitalize_only(thrift_base)
    namespace = hs_namespace or ""

    genfiles = []

    thrift_base = _camel(thrift_base)
    namespace = "/".join([_camel(ns) for ns in namespace.split(".")])
    genfiles.append("%s/Types.hs" % thrift_base)
    for service in services:
        genfiles.append("%s/%s/Client.hs" % (thrift_base, service))
        genfiles.append("%s/%s/Service.hs" % (thrift_base, service))

    gen_paths = [paths.join(namespace, genfile) for genfile in genfiles]
    return {path: paths.join("gen-hs2", path) for path in gen_paths}

def _get_language_rule(
        is_hs2,
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        hs_packages,
        hs2_deps,
        visibility,
        **_kwargs):
    platform = platform_utils.get_platform_for_base_path(base_path)

    srcs = thrift_common.merge_sources_map(sources_map)

    dependencies = []
    if not is_hs2:
        if "new_deps" in options:
            dependencies.extend(_THRIFT_HS_LIBS)
        else:
            dependencies.extend(_THRIFT_HS_LIBS_DEPRECATED)
        dependencies.extend(haskell_rules.get_deps_for_packages(
            _THRIFT_HS_PACKAGES,
            platform,
        ))
    else:
        for services in thrift_srcs.values():
            if services:
                dependencies.extend(_THRIFT_HS2_SERVICE_LIBS)
                break
        dependencies.extend(_THRIFT_HS2_LIBS)
        dependencies.extend(haskell_rules.get_deps_for_packages(
            _THRIFT_HS2_PACKAGES + (hs_packages or []),
            platform,
        ))
        for dep in hs2_deps:
            dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))
    for dep in deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))
    deps, platform_deps = src_and_dep_helpers.format_all_deps(dependencies)
    enable_profiling = True if haskell_common.read_hs_profile() else None

    fb_native.haskell_library(
        name = name,
        visibility = visibility,
        srcs = srcs,
        deps = deps,
        platform_deps = platform_deps,
        enable_profiling = enable_profiling,
    )

def _deprecated_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        hs_packages = (),
        hs2_deps = (),
        visibility = None,
        **kwargs):
    _get_language_rule(
        False,
        base_path = base_path,
        name = name,
        thrift_srcs = thrift_srcs,
        options = options,
        sources_map = sources_map,
        deps = deps,
        hs_packages = hs_packages,
        hs2_deps = hs2_deps,
        visibility = visibility,
        **kwargs
    )

def _hs2_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        hs_packages = (),
        hs2_deps = (),
        visibility = None,
        **kwargs):
    _get_language_rule(
        True,
        base_path = base_path,
        name = name,
        thrift_srcs = thrift_srcs,
        options = options,
        sources_map = sources_map,
        deps = deps,
        hs_packages = hs_packages,
        hs2_deps = hs2_deps,
        visibility = visibility,
        **kwargs
    )

haskell_deprecated_thrift_converter = thrift_interface.make(
    get_lang = _deprecated_get_lang,
    get_compiler = _deprecated_get_compiler,
    get_extra_includes = _get_extra_includes,
    get_names = _deprecated_get_names,
    get_generated_sources = _deprecated_get_generated_sources,
    get_language_rule = _deprecated_get_language_rule,
)

haskell_hs2_thrift_converter = thrift_interface.make(
    get_lang = _hs2_get_lang,
    get_compiler = _hs2_get_compiler,
    get_compiler_args = _hs2_get_compiler_args,
    get_extra_includes = _get_extra_includes,
    get_names = _hs2_get_names,
    get_generated_sources = _hs2_get_generated_sources,
    get_language_rule = _hs2_get_language_rule,
)
