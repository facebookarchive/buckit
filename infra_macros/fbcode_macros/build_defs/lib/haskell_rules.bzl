load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:custom_rule.bzl", "get_project_root_from_gen_dir")
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

C2HS = target_utils.ThirdPartyRuleTarget("stackage-lts", "bin/c2hs")

C2HS_TEMPL = '''\
set -e
mkdir -p `dirname "$OUT"`

# The C/C++ toolchain currently expects we're running from the root of fbcode.
cd {fbcode}

# The `c2hs` tool.
args=($(location {c2hs}))

# Add in the C/C++ preprocessor.
args+=("--cpp="$(cc))

# Add in C/C++ preprocessor flags.
cppflags=(-E)
cppflags+=($(cppflags{deps}))
for cppflag in "${{cppflags[@]}}"; do
  args+=("--cppopts=$cppflag")
done

# The output file and input source.
args+=("-o" "$OUT")
args+=("$SRCS")

exec "${{args[@]}}"
'''

def _c2hs(base_path, name, platform, source, deps, visibility):
    """
    Construct the rules to generate a haskell source from the given `c2hs`
    source.
    """

    # Macros in the `cxx_genrule` below don't support the `platform_deps`
    # parameter that we rely on to support multi-platform builds.  So use
    # a helper rule for this, and just depend on the helper.
    deps_name = name + "-" + source + "-deps"
    d = cpp_common.get_binary_link_deps(base_path, deps_name)
    _dep_rule(base_path, deps_name, deps + d, visibility)
    source_name = name + "-" + source
    fb_native.cxx_genrule(
        name = source_name,
        visibility = get_visibility(visibility, source_name),
        cmd = (
            C2HS_TEMPL.format(
                fbcode = (
                    paths.join(
                        "$GEN_DIR",
                        get_project_root_from_gen_dir(),
                    )
                ),
                c2hs = target_utils.target_to_label(C2HS, platform = platform),
                deps = " :" + deps_name,
            )
        ),
        srcs = [source],
        out = paths.split_extension(source)[0] + ".hs",
    )

    return ":" + source_name

haskell_rules = struct(
    alex_rule = _alex_rule,
    c2hs = _c2hs,
    dep_rule = _dep_rule,
    happy_rule = _happy_rule,
)
