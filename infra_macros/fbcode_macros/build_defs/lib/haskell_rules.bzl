load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_HAPPY = target_utils.ThirdPartyToolRuleTarget("hs-happy", "happy")

def _happy_rule(name, platform, happy_src, visibility):
    """
    Create rules to generate a Haskell source from the given happy file.
    """
    happy_name = name + "-" + happy_src

    fb_native.genrule(
        name = happy_name,
        visibility = get_visibility(visibility, happy_name),
        out = paths.split_extension(happy_src)[0] + ".hs",
        srcs = [happy_src],
        cmd = " && ".join([
            'mkdir -p `dirname "$OUT"`',
            '$(exe {happy}) -o "$OUT" -ag "$SRCS"'.format(
                happy = target_utils.target_to_label(_HAPPY, platform = platform),
            ),
        ]),
    )

    return ":" + happy_name

_ALEX = target_utils.ThirdPartyToolRuleTarget("hs-alex", "alex")

def _alex_rule(name, platform, alex_src, visibility):
    """
    Create rules to generate a Haskell source from the given alex file.
    """
    alex_name = name + "-" + alex_src

    fb_native.genrule(
        name = alex_name,
        visibility = get_visibility(visibility, alex_name),
        out = paths.split_extension(alex_src)[0] + ".hs",
        srcs = [alex_src],
        cmd = " && ".join([
            'mkdir -p `dirname "$OUT"`',
            '$(exe {alex}) -o "$OUT" -g "$SRCS"'.format(
                alex = target_utils.target_to_label(_ALEX, platform = platform),
            ),
        ]),
    )

    return ":" + alex_name

def _dep_rule(base_path, name, deps, visibility):
    """
    Sets up a dummy rule with the given dep objects formatted and installed
    using `deps` and `platform_deps` to support multi-platform builds.

    This is useful to package a given dep list, which requires multi-
    platform dep parameter support, into a single target that can be used
    in interfaces that don't have this support (e.g. macros in `genrule`s
    and `cxx_genrule`).
    """

    # Setup platform default for compilation DB, and direct building.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    lib_deps, lib_platform_deps = src_and_dep_helpers.format_all_deps(deps)

    fb_native.cxx_library(
        name = name,
        visibility = get_visibility(visibility, name),
        preferred_linkage = "static",
        deps = lib_deps,
        platform_deps = lib_platform_deps,
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
    )

haskell_rules = struct(
    alex_rule = _alex_rule,
    dep_rule = _dep_rule,
    happy_rule = _happy_rule,
)
