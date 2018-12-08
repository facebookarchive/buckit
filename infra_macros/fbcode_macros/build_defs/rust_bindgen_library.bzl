load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs/lib:merge_tree.bzl", "merge_tree")
load("@fbcode_macros//build_defs/lib:rust_common.bzl", "rust_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:custom_rule.bzl", "get_project_root_from_gen_dir")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_FLAGFILTER = '''\
# Extract just -D, -I and -isystem options
flagfilter() {{
    while [ $# -gt 0 ]; do
        local f=$1
        shift
        case $f in
            -I?*|-D?*) echo "$f";;
            -I|-D) echo "$f$1"; shift;;
            -isystem) echo "$f $1"; shift;;
            -std=*) echo "$f";;
            -nostdinc) echo "$f";;
            -fno-canonical-system-headers) ;; # skip unknown
            -f*) echo "$f";;
        esac
    done
}}
'''

_PPFLAGS = """
declare -a ppflags
ppflags=($(cxxppflags{deps}))

"""

_CLANG_ARGS = '''\
    \$(flagfilter {base_clang_flags}) \
    {clang_flags} \
    --gcc-toolchain=third-party-buck/{platform}/tools/gcc/ \
    -x c++ \
    \$(flagfilter "${{ppflags[@]}}") \
    -I$(location {includes}) \
'''

_PREPROC_TMPL = \
    _FLAGFILTER + \
    _PPFLAGS + \
    """(
cd {fbcode} && FBPLATFORM={platform} $(cxx)     -o $OUT     -E     $SRCS """ + _CLANG_ARGS + """)
"""

_BINDGEN_TMPL = \
    _FLAGFILTER + \
    _PPFLAGS + \
    '''\
(
TMPFILE=$TMP/bindgen.$$.stderr
trap "rm -f $TMPFILE" EXIT
cd {fbcode} && \
FBPLATFORM={platform} \
$(exe {bindgen}) \
    --output $OUT \
    {bindgen_flags} \
    {blacklist} \
    {opaque} \
    {wl_funcs} \
    {wl_types} \
    {wl_vars} \
    {generate} \
    $SRCS \
    -- \
''' + _CLANG_ARGS + """2> $TMPFILE || (e=$?; cat $TMPFILE 1>&2; exit $e)
)
"""

def _get_exported_include_tree(name):
    return name + "-bindgen-includes"

def _get_genrule_cmd(
        template,
        name,
        platform,
        bindgen_flags,
        base_clang_flags,
        clang_flags,
        blacklist_types,
        opaque_types,
        whitelist_types,
        whitelist_funcs,
        whitelist_vars,
        generate,
        cpp_deps):
    return template.format(
        fbcode = paths.join("$GEN_DIR", get_project_root_from_gen_dir()),
        bindgen = third_party.get_tool_target("rust-bindgen", None, "bin/bindgen", platform),
        bindgen_flags = " ".join([shell.quote(flag) for flag in bindgen_flags]),
        base_clang_flags = " ".join([shell.quote(flag) for flag in base_clang_flags]),
        clang_flags = " ".join([shell.quote(flag) for flag in clang_flags]),
        blacklist = " ".join([
            "--blacklist-type " + shell.quote(ty)
            for ty in blacklist_types
        ]),
        opaque = " ".join([
            "--opaque-type " + shell.quote(ty)
            for ty in opaque_types
        ]),
        wl_types = " ".join([
            "--whitelist-type " + shell.quote(ty)
            for ty in whitelist_types
        ]),
        wl_funcs = " ".join([
            "--whitelist-function " + shell.quote(fn)
            for fn in whitelist_funcs
        ]),
        wl_vars = " ".join([
            "--whitelist-var " + shell.quote(v)
            for v in whitelist_vars
        ]),
        generate = generate,
        deps = "".join([" " + d for d in cpp_deps]),
        includes = _get_exported_include_tree(":" + name),
        platform = platform,
    )

def _generate_bindgen_rule(
        base_path,
        name,
        header,
        cpp_deps,
        cxx_namespaces = False,
        blacklist_types = (),
        opaque_types = (),
        whitelist_funcs = (),
        whitelist_types = (),
        whitelist_vars = (),
        bindgen_flags = None,
        clang_flags = (),
        generate = (),
        src_includes = None,
        **kwargs):
    _ignore = kwargs

    src = "lib.rs"
    gen_name = name + "-bindgen"

    # TODO(T27678070): The Rust bindgen rule should inherit it's platform
    # from top-level rules, not look it up via a PLATFORM file.  We should
    # cleanup all references to this in the code below.
    platform = platform_utils.get_platform_for_base_path(base_path)

    if generate:
        generate = "--generate " + ",".join(generate)
    else:
        generate = ""

    base_bindgen_flags = [
        "--raw-line=#![allow(non_snake_case)]",
        "--raw-line=#![allow(non_camel_case_types)]",
        "--raw-line=#![allow(non_upper_case_globals)]",
        '--raw-line=#[link(name = "stdc++")] extern {}',
    ]

    # Include extra sources the user wants.
    # We need to make the include path absolute, because otherwise rustc
    # will interpret as relative to the source that's including it, which
    # is in the cxx_genrule build dir.
    for s in (src_includes or []):
        base_bindgen_flags.append(
            '--raw-line=include!(concat!(env!("RUSTC_BUILD_CONTAINER"), "{}"));'
                .format(paths.join(base_path, s)),
        )

    if cxx_namespaces:
        base_bindgen_flags.append("--enable-cxx-namespaces")
    bindgen_flags = base_bindgen_flags + (bindgen_flags or [])

    # rust-bindgen is clang-based, so we can't directly use the cxxppflags
    # in a gcc build. This means we need to fetch the appropriate flags
    # here, and also filter out inappropriate ones we get from the
    # $(cxxppflags) macro in the cxxgenrule.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    base_clang_flags = "%s %s" % (
        native.read_config("rust#" + buck_platform, "bindgen_cxxppflags"),
        native.read_config("rust#" + buck_platform, "bindgen_cxxflags"),
    )
    base_clang_flags = base_clang_flags.split(" ")

    # Actual bindgen rule
    fb_native.cxx_genrule(
        name = gen_name,
        out = paths.join(common_paths.CURRENT_DIRECTORY, src),
        srcs = [header],
        visibility = [],
        bash = _get_genrule_cmd(
            template = _BINDGEN_TMPL,
            name = name,
            platform = platform,
            bindgen_flags = bindgen_flags,
            base_clang_flags = base_clang_flags,
            clang_flags = clang_flags,
            blacklist_types = blacklist_types,
            opaque_types = opaque_types,
            whitelist_types = whitelist_types,
            whitelist_funcs = whitelist_funcs,
            whitelist_vars = whitelist_vars,
            generate = generate,
            cpp_deps = cpp_deps,
        ),
    )

    # Rule to generate pre-processed output, to make debugging
    # bindgen problems easier.

    fb_native.cxx_genrule(
        name = name + "-preproc",
        out = paths.join(common_paths.CURRENT_DIRECTORY, name + ".i"),
        srcs = [header],
        bash = _get_genrule_cmd(
            template = _PREPROC_TMPL,
            name = name,
            platform = platform,
            bindgen_flags = bindgen_flags,
            base_clang_flags = base_clang_flags,
            clang_flags = clang_flags,
            blacklist_types = blacklist_types,
            opaque_types = opaque_types,
            whitelist_types = whitelist_types,
            whitelist_funcs = whitelist_funcs,
            whitelist_vars = whitelist_vars,
            generate = generate,
            cpp_deps = cpp_deps,
        ),
    )

    return ":{}".format(gen_name)

def _convert(
        name,
        header,
        cpp_deps,
        deps = (),
        src_includes = None,
        visibility = None,
        **kwargs):
    base_path = native.package_name()

    # Setup the exported include tree to dependents.
    merge_tree(
        base_path,
        _get_exported_include_tree(name),
        [header],
        [],
        visibility,
    )

    genrule = _generate_bindgen_rule(
        base_path,
        name,
        header,
        [src_and_dep_helpers.convert_build_target(base_path, d) for d in cpp_deps],
        src_includes = src_includes,
        **kwargs
    )

    # Use normal converter to make build+test rules
    rust_lib_attrs = rust_common.convert_rust(
        name,
        fbconfig_rule_type = "rust_bindgen_library",
        srcs = [genrule] + (src_includes or []),
        deps = list(cpp_deps) + list(deps),
        crate_root = genrule,
        visibility = visibility,
        **kwargs
    )
    fb_native.rust_library(**rust_lib_attrs)

def rust_bindgen_library(
        name,
        header,
        cpp_deps,
        deps = (),
        external_deps = None,
        src_includes = None,
        generate = None,
        cxx_namespaces = None,
        opaque_types = (),
        blacklist_types = (),
        whitelist_funcs = (),
        whitelist_types = (),
        whitelist_vars = (),
        bindgen_flags = None,
        clang_flags = (),
        rustc_flags = None,
        link_style = None,
        linker_flags = None,
        visibility = None,
        licenses = None):
    _convert(
        name = name,
        header = header,
        cpp_deps = cpp_deps,
        deps = deps,
        external_deps = external_deps,
        src_includes = src_includes,
        generate = generate,
        cxx_namespaces = cxx_namespaces,
        opaque_types = opaque_types,
        blacklist_types = blacklist_types,
        whitelist_funcs = whitelist_funcs,
        whitelist_types = whitelist_types,
        whitelist_vars = whitelist_vars,
        bindgen_flags = bindgen_flags,
        clang_flags = clang_flags,
        rustc_flags = rustc_flags,
        link_style = link_style,
        linker_flags = linker_flags,
        visibility = get_visibility(visibility, name),
        licenses = licenses,
    )
