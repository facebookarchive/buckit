"""
Specializer to support generating Rust libraries from thrift sources.
This is a two-stage process; we use the Haskell hs2 compiler to generate
a JSON representation of the AST, and then a Rust code generator to
generate code from that.

Here, the "compiler" is the .thrift -> .ast (json) conversion, and the
language rule is ast -> {types, client, server, etc crates} -> unified crate
where the unified crate simply re-exports the other crates (the other
crates are useful for downstream dependencies which don't need everything)
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:custom_rule.bzl", "get_project_root_from_gen_dir")
load("@fbcode_macros//build_defs:rust_library.bzl", "rust_library")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_RUST_AST_CODEGEN_FLAGS = (
    "--add_serde_derives"
)

# Make sure this doesn't have any duplicates
_RUST_KEYWORDS = [
    "abstract",
    "alignof",
    "as",
    "become",
    "box",
    "break",
    "const",
    "continue",
    "crate",
    "do",
    "else",
    "enum",
    "extern",
    "false",
    "final",
    "fn",
    "for",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "macro",
    "match",
    "mod",
    "move",
    "mut",
    "offsetof",
    "override",
    "priv",
    "proc",
    "pub",
    "pure",
    "ref",
    "return",
    "Self",
    "self",
    "sizeof",
    "static",
    "struct",
    "super",
    "trait",
    "true",
    "type",
    "typeof",
    "unsafe",
    "unsized",
    "use",
    "virtual",
    "where",
    "while",
    "yield",
]

def _format_options(options):
    args = []
    for option, val in options.items():
        flag = "--" + option
        if val != None:
            flag += "=" + val
        args.append(flag)
    return args

def _get_ast_to_rust(name, options, sources_map, deps, visibility):
    sources = thrift_common.merge_sources_map(sources_map).values()
    crate_maps = [
        "--crate-map-file $(location {}-crate-map)".format(dep)
        for dep in deps
    ]

    # Hacky hack to deal with `codegen`s dynamic dependency on
    # proc_macro.so in the rust libraries, via the `quote` crate.
    # At least avoid hard-coding platform and arch.
    rustc_path = paths.join(
        "$GEN_DIR",
        get_project_root_from_gen_dir(),
        third_party.get_tool_path(
            "rust/lib/rustlib/{arch}/lib/"
                .format(arch = "x86_64-unknown-linux-gnu"),
            "platform007",
        ),
    )
    cmd = (
        "env LD_LIBRARY_PATH=\$(realpath {rustc}) " +
        "$(exe //common/rust/thrift/compiler:codegen) -o $OUT " +
        "{crate_maps} {options} {sources}; /bin/rustfmt $OUT"
    ).format(
        rustc = rustc_path,
        sources = " ".join(["$(location {})".format(src) for src in sources]),
        options = " ".join(_format_options(options)),
        crate_maps = " ".join(crate_maps),
    )

    # generated file: <name>/lib.rs

    fb_native.genrule(
        name = "%s-gen-rs" % name,
        labels = ["generated"],
        visibility = visibility,
        out = "{}/{}/lib.rs".format(common_paths.CURRENT_DIRECTORY, name),
        srcs = sources,
        cmd = cmd,
    )

def _get_rust_to_rlib(
        name,
        options,
        deps,
        visibility,
        features = None,
        rustc_flags = None,
        crate_root = None,
        tests = None,
        test_deps = None,
        test_external_deps = None,
        test_srcs = None,
        test_features = None,
        test_rustc_flags = None,
        test_link_style = None,
        preferred_linkage = None,
        proc_macro = False,
        licenses = None):
    out_deps = [
        "//common/rust/thrift/runtime:rust_thrift",
    ]
    out_external_deps = [
        ("rust-crates-io", None, "error-chain"),
        ("rust-crates-io", None, "futures"),
        ("rust-crates-io", None, "lazy_static"),
        ("rust-crates-io", None, "tokio-service"),
    ]

    if "add_serde_derives" in options:
        out_external_deps += [
            ("rust-crates-io", None, "serde_derive"),
            ("rust-crates-io", None, "serde"),
        ]

    out_deps += deps
    crate_name = _rust_crate_name(name)

    rust_library(
        name = name,
        srcs = [":%s-gen-rs" % name],
        deps = out_deps,
        external_deps = out_external_deps,
        unittests = False,  # nothing meaningful
        crate = crate_name,
        visibility = visibility,
        features = features,
        rustc_flags = rustc_flags,
        crate_root = crate_root,
        tests = tests,
        test_deps = test_deps,
        test_external_deps = test_external_deps,
        test_srcs = test_srcs,
        test_features = test_features,
        test_rustc_flags = test_rustc_flags,
        test_link_style = test_link_style,
        preferred_linkage = preferred_linkage,
        proc_macro = proc_macro,
        licenses = licenses,
    )

def _rust_crate_name(name):
    # Always name crate after rule - remapping will sort things out
    crate_name = name.rsplit("-", 1)[0].replace("-", "_")
    if crate_name in _RUST_KEYWORDS:
        crate_name += "_"
    return crate_name

def _get_rust_crate_map(base_path, name, thrift_srcs, visibility):
    # Generate a mapping from thrift file to crate and module. The
    # file format is:
    # thrift_path crate_name crate_alias [module]
    #
    # For single-thrift-file targets, we put it at the top of the namespace
    # so users will likely want to alias the crate name to the thrift file
    # name on import. For multi-thrift files, we put each file in its own
    # module - the crate is named after the target, and the references are
    # into the submodules.
    crate_name = _rust_crate_name(name)

    crate_map = []
    for src in thrift_srcs.keys():
        src = paths.join(base_path, src_and_dep_helpers.get_source_name(src))
        modname = paths.split_extension(paths.basename(src))[0]
        if len(thrift_srcs) > 1:
            crate_map.append("{} {} {} {}"
                .format(src, crate_name, crate_name, modname))
        else:
            crate_map.append("{} {} {}".format(src, crate_name, modname))

    crate_map_name = "%s-crate-map" % name

    cmd = "mkdir -p `dirname $OUT` && echo {0} > $OUT".format(shell.quote("\n".join(crate_map)))
    fb_native.genrule(
        name = crate_map_name,
        labels = ["generated"],
        visibility = visibility,
        out = paths.join(common_paths.CURRENT_DIRECTORY, crate_map_name + ".txt"),
        cmd = cmd,
    )

def _get_lang():
    return "rust"

def _get_names():
    return ("rust",)

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        rs_namespace = None,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = services
    _ignore = options
    thrift_base = paths.split_extension(
        paths.basename(
            src_and_dep_helpers.get_source_name(thrift_src),
        ),
    )[0]
    namespace = rs_namespace or ""

    genfiles = [paths.join(namespace, "%s.ast" % thrift_base)]

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
    # Construct some rules:
    # json -> rust
    # rust -> rlib

    _get_ast_to_rust(
        name,
        options,
        sources_map,
        deps,
        visibility,
    )
    _get_rust_to_rlib(
        name,
        options,
        deps,
        visibility,
    )
    _get_rust_crate_map(
        base_path,
        name,
        thrift_srcs,
        visibility,
    )

def _get_compiler_args(
        compiler_lang,
        flags,
        options,
        **_kwargs):
    _ignore = compiler_lang

    # Format the options and pass them into the hs2 compiler.
    args = ["--emit-json", "--rust"] + _format_options(options)

    # Exclude AST specific flags,
    # that are needed for get_ast_to_rust only
    args = [arg for arg in args if arg not in _RUST_AST_CODEGEN_FLAGS]

    # Include rule-specific flags.
    args.extend([flag for flag in flags if flag not in ("--strict")])

    return args

def _get_compiler():
    return config.get_thrift_hs2_compiler()

rust_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_names = _get_names,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
    get_compiler = _get_compiler,
    get_compiler_args = _get_compiler_args,
)
