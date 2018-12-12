load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib/swig:go_converter.bzl", "go_converter")
load("@fbcode_macros//build_defs/lib/swig:java_converter.bzl", "java_converter")
load("@fbcode_macros//build_defs/lib/swig:python_converter.bzl", "python_converter")
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs/lib:copy_rule.bzl", "copy_rule")
load("@fbcode_macros//build_defs/lib:merge_tree.bzl", "merge_tree")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load(
    "@fbsource//tools/build_defs:fb_native_wrapper.bzl",
    "fb_native",
)

_FLAGS = [
    "-c++",
    "-Werror",
    "-Wextra",
]

_LANG_CONVERTERS = (
    java_converter,
    go_converter,
    python_converter,
)
_CONVERTERS = {c.get_lang(): c for c in _LANG_CONVERTERS}

def _get_languages(langs):
    """
    Convert the `languages` parameter to a normalized list of languages.
    """

    languages = []

    if langs == None:
        fail("swig_library() requires `languages` argument")

    if not langs:
        fail("swig_library() requires at least on language")

    for lang in langs:
        if lang not in _CONVERTERS:
            fail(
                "swig_library() does not support language {!r}"
                    .format(lang),
            )
        if lang in languages:
            fail(
                "swig_library() given duplicate language {!r}"
                    .format(lang),
            )
        languages.append(lang)

    return languages

def _get_exported_include_tree(dep):
    """
    Generate the exported swig source includes target use for the given
    swig library target.
    """

    return dep + "-swig-includes"

def _generate_compile_rule(
        base_path,
        name,
        swig_flags,
        lang,
        interface,
        cpp_deps,
        visibility,
        **kwargs):
    """
    Generate a rule which runs the swig compiler for the given inputs.
    """
    platform = platform_utils.get_platform_for_base_path(base_path)
    converter = _CONVERTERS[lang]
    base, _ = paths.split_extension(src_and_dep_helpers.get_source_name(interface))
    hdr = base + ".h"
    src = base + ".cc"

    flags = []
    flags.extend(_FLAGS)
    flags.extend(swig_flags)
    flags.extend(converter.get_lang_flags(**kwargs))

    gen_name = "{}-{}-gen".format(name, lang)
    cmds = [
        "mkdir -p" +
        ' "$OUT"/lang' +
        ' \\$(dirname "$OUT"/gen/{src})' +
        ' \\$(dirname "$OUT"/gen/{hdr})',
        "export PPFLAGS=(`" +
        " $(exe //tools/build/buck:swig_pp_filter)" +
        " $(cxxppflags{deps})`)",
        'touch "$OUT"/gen/{hdr}',
        "$(exe {swig}) {flags} {lang}" +
        " -I- -I$(location {includes})" +
        ' "${{PPFLAGS[@]}}"' +
        ' -outdir "$OUT"/lang -o "$OUT"/gen/{src} -oh "$OUT"/gen/{hdr}' +
        ' "$SRCS"',
    ]
    fb_native.cxx_genrule(
        name = gen_name,
        visibility = get_visibility(visibility, gen_name),
        out = common_paths.CURRENT_DIRECTORY,
        srcs = [interface],
        cmd = (
            " && ".join(cmds).format(
                swig = third_party.get_tool_target("swig", None, "bin/swig", platform),
                flags = " ".join([shell.quote(flag) for flag in flags]),
                lang = shell.quote(converter.get_lang_opt()),
                includes = _get_exported_include_tree(":" + name),
                deps = "".join([" " + d for d in src_and_dep_helpers.format_deps(cpp_deps)]),
                hdr = shell.quote(hdr),
                src = shell.quote(src),
            )
        ),
    )

    gen_hdr_name = gen_name + "=" + hdr
    copy_rule(
        "$(location :{})/gen/{}".format(gen_name, hdr),
        gen_hdr_name,
        hdr,
        propagate_versions = True,
    )

    gen_src_name = gen_name + "=" + src
    copy_rule(
        "$(location :{})/gen/{}".format(gen_name, src),
        gen_src_name,
        src,
        propagate_versions = True,
    )

    return (
        ":{}".format(gen_name),
        ":" + gen_hdr_name,
        ":" + gen_src_name,
    )

def _generate_generated_source_rules(name, src_name, srcs, visibility):
    """
    Create rules to extra individual sources out of the directory of swig
    sources the compiler generated.
    """

    out = {}

    for sname, src in srcs.items():
        gen_name = "{}={}".format(name, src)
        fb_native.cxx_genrule(
            name = gen_name,
            visibility = get_visibility(visibility, gen_name),
            out = src,
            cmd = " && ".join([
                "mkdir -p `dirname $OUT`",
                "cp -rd $(location {})/lang/{} $OUT".format(src_name, src),
            ]),
        )
        out[sname] = ":" + gen_name

    return out

def _convert_macros(
        base_path,
        name,
        interface,
        module = None,
        languages = (),
        swig_flags = (),
        cpp_deps = (),
        ext_deps = (),
        ext_external_deps = (),
        deps = (),
        visibility = None,
        **kwargs):
    """
    Swig library conversion implemented purely via macros (i.e. no Buck
    support).
    """

    # Parse incoming options.
    languages = _get_languages(languages)
    cpp_deps = [target_utils.parse_target(d, default_base_path = base_path) for d in cpp_deps]
    ext_deps = (
        [target_utils.parse_target(d, default_base_path = base_path) for d in ext_deps] +
        [src_and_dep_helpers.normalize_external_dep(d) for d in ext_external_deps]
    )

    if module == None:
        module = name

    # Setup the exported include tree to dependents.
    merge_tree(
        base_path,
        _get_exported_include_tree(name),
        [interface],
        [_get_exported_include_tree(dep) for dep in deps],
        visibility = visibility,
    )

    # Generate rules for all supported languages.
    for lang in languages:
        converter = _CONVERTERS[lang]

        # Generate the swig compile rules.
        compile_rule, hdr, src = (
            _generate_compile_rule(
                base_path,
                name,
                swig_flags,
                lang,
                interface,
                cpp_deps,
                visibility = visibility,
                **kwargs
            )
        )

        # Create wrapper rules to extract individual generated sources
        # and expose via target refs in the UI.
        gen_srcs = converter.get_generated_sources(module)
        gen_srcs = (
            _generate_generated_source_rules(
                "{}-{}-src".format(name, lang),
                compile_rule,
                gen_srcs,
                visibility = visibility,
            )
        )

        # Generate the per-language rules.
        converter.get_language_rule(
            base_path,
            name + "-" + lang,
            module,
            hdr,
            src,
            gen_srcs,
            sorted(cpp_deps + ext_deps),
            [dep + "-" + lang for dep in deps],
            visibility = visibility,
            **kwargs
        )

def swig_library(
        name,
        cpp_deps = (),
        ext_deps = (),
        ext_external_deps = (),
        deps = (),
        interface = None,
        java_library_name = None,
        java_link_style = None,
        java_package = None,
        languages = (),
        module = None,
        py_base_module = None,
        go_package_name = None,
        swig_flags = (),
        visibility = None):
    _convert(
        name = name,
        cpp_deps = cpp_deps,
        ext_deps = ext_deps,
        ext_external_deps = ext_external_deps,
        deps = deps,
        interface = interface,
        java_library_name = java_library_name,
        java_link_style = java_link_style,
        java_package = java_package,
        languages = languages,
        module = module,
        py_base_module = py_base_module,
        go_package_name = go_package_name,
        swig_flags = swig_flags,
        visibility = visibility,
    )

def _convert(name, visibility = None, **kwargs):
    base_path = native.package_name()
    visibility = get_visibility(visibility, name)

    # Convert rules we support via macros.
    macro_languages = _get_languages(kwargs.get("languages"))
    if macro_languages:
        _convert_macros(base_path, name = name, visibility = visibility, **kwargs)
