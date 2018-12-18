load("@bazel_skylib//lib:collections.bzl", "collections")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:cpp2.bzl", "cpp2_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:d.bzl", "d_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:go.bzl", "go_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:haskell.bzl", "haskell_deprecated_thrift_converter", "haskell_hs2_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:java.bzl", "java_deprecated_apache_thrift_converter", "java_deprecated_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:js.bzl", "js_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:ocaml.bzl", "ocaml_thrift_converter")
load(
    "@fbcode_macros//build_defs/lib/thrift:python.bzl",
    "python_asyncio_thrift_converter",
    "python_normal_thrift_converter",
    "python_pyi_asyncio_thrift_converter",
    "python_pyi_thrift_converter",
    "python_twisted_thrift_converter",
)
load("@fbcode_macros//build_defs/lib/thrift:python3.bzl", "python3_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:rust.bzl", "rust_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:swift.bzl", "swift_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:thriftdoc_python.bzl", "thriftdoc_python_thrift_converter")
load("@fbcode_macros//build_defs/lib:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs/lib:merge_tree.bzl", "merge_tree")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_list", "is_string", "is_tuple")

_PY_REMOTES_EXTERNAL_DEPS = (
    "python-future",
    "six",
)

def _instantiate_converters():
    all_converters = [
        cpp2_thrift_converter,
        d_thrift_converter,
        go_thrift_converter,
        haskell_deprecated_thrift_converter,
        haskell_hs2_thrift_converter,
        js_thrift_converter,
        ocaml_thrift_converter,
        rust_thrift_converter,
        thriftdoc_python_thrift_converter,
        python3_thrift_converter,
        python_normal_thrift_converter,
        python_twisted_thrift_converter,
        python_asyncio_thrift_converter,
        python_pyi_thrift_converter,
        python_pyi_asyncio_thrift_converter,
        java_deprecated_thrift_converter,
        java_deprecated_apache_thrift_converter,
        swift_thrift_converter,
    ]
    converters = {}
    name_to_lang = {}
    for converter in all_converters:
        converters[converter.get_lang()] = converter
        for name in converter.get_names():
            name_to_lang[name] = converter.get_lang()

    return converters, name_to_lang

# TODO: Make private
CONVERTERS, NAMES_TO_LANG = _instantiate_converters()

# TODO: Make private
def generate_generated_source_rules(compile_name, srcs, visibility):
    """
    Create rules to extra individual sources out of the directory of thrift
    sources the compiler generated.
    """

    out = {}

    for name, src in srcs.items():
        cmd = " && ".join([
            "mkdir -p `dirname $OUT`",
            "cp -R $(location :{})/{} $OUT".format(compile_name, src),
        ])
        genrule_name = "{}={}".format(compile_name, src)
        fb_native.genrule(
            name = genrule_name,
            labels = ["generated"],
            visibility = visibility,
            out = src,
            cmd = cmd,
        )
        out[name] = ":" + genrule_name

    return out

# TODO: Make private
def get_languages(names):
    """
    Convert the `languages` parameter to a normalized list of languages.
    """

    languages = {}

    for name in names:
        lang = NAMES_TO_LANG.get(name)
        if lang == None:
            fail("thrift_library() does not support language {}".format(name))
        if lang in languages:
            fail("thrift_library() given duplicate language {}".format(lang))
        languages[lang] = None

    return languages

# TODO: Make private
def generate_compile_rule(
        name,
        compiler,
        lang,
        compiler_args,
        source,
        postprocess_cmd = None,
        visibility = None):
    """
    Generate a rule which runs the thrift compiler for the given inputs.
    """

    genrule_name = (
        "{}-{}-{}".format(name, lang, src_and_dep_helpers.get_source_name(source))
    )
    cmds = []
    converter = CONVERTERS[lang]
    cmds.append(
        converter.get_compiler_command(
            compiler,
            compiler_args,
            get_exported_include_tree(":" + name),
            converter.get_additional_compiler(),
        ),
    )

    if postprocess_cmd != None:
        cmds.append(postprocess_cmd)

    fb_native.genrule(
        name = genrule_name,
        labels = ["generated"],
        visibility = visibility,
        out = common_paths.CURRENT_DIRECTORY,
        srcs = [source],
        cmd = " && ".join(cmds),
    )
    return genrule_name

# TODO: Make private
def filter_language_specific_kwargs(**kwargs):
    """
    Filter out kwargs that aren't actually present

    We want to define all of our possible arguments up front for discoverability by
    users, however some converters would like to specify their own defaults for
    various functions if the kwarg wasn't provided. (e.g. cpp2_srcs, or
    javadeprecated_maven_publisher_version_prefix. So, filter out any of the kwargs
    that are == None (unspecified), and rely on rules to specify their own defaults.
    """

    return {k: v for k, v in kwargs.items() if v != None}

# TODO: Make private
def get_exported_include_tree(dep):
    """
    Generate the exported thrift source includes target use for the given
    thrift library target.
    """
    return dep + "-thrift-includes"

# TODO: Make private
# TODO: Remove the need for this by making this a list everywhere
def parse_thrift_args(args):
    """
    For some reason we accept `thrift_args` as either a list or
    space-separated string.
    """

    if is_string(args):
        args = args.split()

    return args

# TODO: Make private
def fixup_thrift_srcs(srcs):
    """ Normalize the format of the thrift_srcs attribute """
    new_srcs = {}
    for name, services in sorted(srcs.items()):
        if services == None:
            services = []
        elif not is_tuple(services) and not is_list(services):
            services = [services]
        new_srcs[name] = services
    return new_srcs

# TODO: Make private
def parse_thrift_options(options):
    """
    Parse the option list or string into a dict.
    """

    parsed = {}

    if is_string(options):
        options = options.split(",")

    for option in options:
        if "=" in option:
            option, val = option.rsplit("=", 1)
            parsed[option] = val
        else:
            parsed[option] = None

    return parsed

def convert_macros(
        base_path,
        name,
        thrift_srcs,
        thrift_args,
        deps,
        languages,
        visibility,
        plugins,
        **language_kwargs):
    """
    Thrift library conversion implemented purely via macros (i.e. no Buck
    support).
    """

    # Setup the exported include tree to dependents.
    includes = []
    includes.extend(thrift_srcs.keys())
    for lang in languages:
        converter = CONVERTERS[lang]
        includes.extend(converter.get_extra_includes(**language_kwargs))

    merge_tree(
        base_path,
        get_exported_include_tree(name),
        sorted(collections.uniq(includes)),
        [get_exported_include_tree(dep) for dep in deps],
        labels = ["generated"],
        visibility = visibility,
    )

    # py3 thrift requires cpp2
    if "py3" in languages and "cpp2" not in languages:
        languages["cpp2"] = None

    # save cpp2_options for later use by 'py3'
    cpp2_options = ()
    py_options = ()
    py_asyncio_options = ()
    if "cpp2" in languages:
        cpp2_options = parse_thrift_options(
            language_kwargs.get("thrift_cpp2_options", ()),
        )

    # Types are generated for all legacy Python Thrift
    if "py" in languages:
        languages["pyi"] = None

        # Save the options for pyi to use
        py_options = parse_thrift_options(language_kwargs.get("thrift_py_options", ()))

    if "py-asyncio" in languages:
        languages["pyi-asyncio"] = None

        # Save the options for pyi to use
        py_asyncio_options = parse_thrift_options(language_kwargs.get("thrift_py_asyncio_options", ()))

    # Generate rules for all supported languages.
    for lang in languages:
        converter = CONVERTERS[lang]
        compiler = converter.get_compiler()
        options = (
            parse_thrift_options(
                language_kwargs.get("thrift_{}_options".format(
                    lang.replace("-", "_"),
                ), ()),
            )
        )
        if lang == "pyi":
            options.update(py_options)
        if lang == "pyi-asyncio":
            options.update(py_asyncio_options)
        if lang == "py3":
            options.update(cpp2_options)

        compiler_args = converter.get_compiler_args(
            converter.get_compiler_lang(),
            thrift_args,
            converter.get_options(base_path, options),
            **language_kwargs
        )

        all_gen_srcs = {}
        for thrift_src, services in thrift_srcs.items():
            thrift_name = src_and_dep_helpers.get_source_name(thrift_src)

            # Generate the thrift compile rules.
            compile_rule_name = (
                generate_compile_rule(
                    name,
                    compiler,
                    lang,
                    compiler_args,
                    thrift_src,
                    converter.get_postprocess_command(
                        base_path,
                        thrift_name,
                        "$OUT",
                        **language_kwargs
                    ),
                    visibility = visibility,
                )
            )

            # Create wrapper rules to extract individual generated sources
            # and expose via target refs in the UI.
            gen_srcs = (
                converter.get_generated_sources(
                    base_path,
                    name,
                    thrift_name,
                    services,
                    options,
                    visibility = visibility,
                    **language_kwargs
                )
            )
            gen_srcs = generate_generated_source_rules(
                compile_rule_name,
                gen_srcs,
                visibility = visibility,
            )
            all_gen_srcs[thrift_name] = gen_srcs

        # Generate rules from Thrift plugins
        for plugin in plugins:
            plugin.generate_rules(
                plugin,
                base_path,
                name,
                lang,
                thrift_srcs,
                compiler_args,
                get_exported_include_tree(":" + name),
                deps,
            )

        # Generate the per-language rules.
        converter.get_language_rule(
            base_path,
            name + "-" + lang,
            thrift_srcs,
            options,
            all_gen_srcs,
            [dep + "-" + lang for dep in deps],
            visibility = visibility,
            **language_kwargs
        )

# TODO: Make private
def py_remote_binaries(
        base_path,
        name,
        thrift_srcs,
        base_module,
        visibility,
        include_sr = False):
    """
    Generate binaries for py-remote support
    """

    # Find and normalize the base module.
    if base_module == None:
        base_module = base_path
    base_module = base_module.replace("/", ".")

    for thrift_src, services in thrift_srcs.items():
        thrift_base = (
            paths.split_extension(
                paths.basename(src_and_dep_helpers.get_source_name(thrift_src)),
            )[0]
        )
        for service in services:
            if include_sr:
                sr_rule = "//thrift/facebook/remote/sr:remote"
            else:
                sr_rule = "//thrift/lib/py/util:remote"
            main_module = ".".join([
                element
                for element in [
                    base_module,
                    thrift_base,
                    service + "-remote",
                ]
                if element
            ])
            python_binary(
                name = "{}-{}-pyremote".format(name, service),
                visibility = visibility,
                py_version = "<3",
                base_module = "",
                main_module = main_module,
                deps = [
                    ":{}-py".format(name),
                    sr_rule,
                ],
                external_deps = _PY_REMOTES_EXTERNAL_DEPS,
            )
