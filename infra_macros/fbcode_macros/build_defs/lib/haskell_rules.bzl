load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:config.bzl", "config")
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

HSC2HS_TEMPL = '''\
set -e
mkdir -p `dirname "$OUT"`

# The C/C++ toolchain currently expects we're running from the root of fbcode.
cd {fbcode}

# The `hsc2hs` tool.
args=({ghc_tool}/bin/hsc2hs)

# Keep hsc2hs's internal files around, since this is useful for debugging and
# doesn't hurt us.
args+=("--keep-files")

args+=("--template=template-hsc.h")

# Always define __HSC2HS__ in the C program and the compiled Haskell file, and
# the C header.
args+=("--define=__HSC2HS__")

# We need to pass "-x c++" to the compiler that hsc2hs invokes, but *before*
# any file paths; hsc2hs passes flags *after* paths. The easy and morally
# tolerable workaround is to generate a shell script that partially applies
# the flag.
CC_WRAP="$OUT".cc_wrap.sh
echo >  "$CC_WRAP" '#!/bin/sh'

# TODO: T23700463 Turn distcc back on
echo >> "$CC_WRAP" 'BUCK_DISTCC=0 $(cxx) -x c++ "$@"'
chmod +x "$CC_WRAP"
# Set 'CXX' locally to the real compiler being invoked, so that hsc2hs plugins
# needing to invoke the compiler can do so correctly.
export CXX="$CC_WRAP"
args+=("--cc=$CC_WRAP")

# Pass in the C/C++ compiler and preprocessor flags.
cflags=()
cflags+=("-fpermissive")
cflags+=($(cxxflags))
cflags+=($(cxxppflags{deps}))
ltoflag=""
# Needed for `template-hsc.h`.
cflags+=(-I{ghc}/lib)
for cflag in "${{cflags[@]}}"; do
  if [[ "$cflag" == "-flto" || "$cflag" =~ "-flto=" ]]; then
    ltoflag="$cflag"
  fi
  args+=(--cflag="$cflag")
done

# Add in the C/C++ linker.
args+=("--ld=$(ld)")

# Add in the linker flags.
ldflags=($(ldflags-{link_style}{deps}))
if [ ! -z "$ltoflag" ]; then
    ldflags+=("$ltoflag")
fi
ldflags+=("-o" "`dirname $OUT`/{out_obj}")
for ldflag in "${{ldflags[@]}}"; do
  args+=(--lflag="$ldflag")
done

# Link the "run once" hsc2hs binary stripped. This makes some hsc files
# go from 20s to 10s and the "run once" binary from 800M to 40M when
# statically linked. Situations where one would want to debug them are
# very rare.
# This doesn't make a difference when dynamically linked.
args+=("--lflag=-Xlinker")
args+=("--lflag=-s")

# When linking in `dev` mode, make sure that the ASAN symbols that get linked
# into the top-level binary are made available for any dependent libraries.
if [ "{link_style}" == "shared" ]; then
  args+=("--lflag=-Xlinker")
  args+=("--lflag=--export-dynamic")
fi;

# The output file and input source.
args+=("-o" "$OUT")
args+=("$SRCS")

exec "${{args[@]}}"
'''

def _hsc2hs(
        base_path,
        name,
        platform,
        source,
        deps,
        visibility):
    """
    Construct the rules to generate a haskell source from the given
    `hsc2hs` source.
    """

    # Macros in the `cxx_genrule` below don't support the `platform_deps`
    # parameter that we rely on to support multi-platform builds.  So use
    # a helper rule for this, and just depend on the helper.
    deps_name = name + "-" + source + "-deps"
    d = cpp_common.get_binary_link_deps(base_path, deps_name)
    _dep_rule(base_path, deps_name, deps + d, visibility)

    out_obj = paths.split_extension(paths.basename(source))[0] + "_hsc_make"
    source_name = name + "-" + source
    fb_native.cxx_genrule(
        name = source_name,
        visibility = get_visibility(visibility, source_name),
        cmd = (
            HSC2HS_TEMPL.format(
                fbcode = (
                    paths.join(
                        "$GEN_DIR",
                        get_project_root_from_gen_dir(),
                    )
                ),
                ghc_tool = third_party.get_tool_path("ghc", platform),
                ghc = paths.join(third_party.get_build_path(platform), "ghc"),
                link_style = config.get_default_link_style(),
                deps = " :" + deps_name,
                out_obj = out_obj,
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
    hsc2hs = _hsc2hs,
)
