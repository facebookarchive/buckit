load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
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

haskell_rules = struct(
    alex_rule = _alex_rule,
    happy_rule = _happy_rule,
)
