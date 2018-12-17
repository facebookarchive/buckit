"""
Specializer to support generating Java Swift libraries from thrift sources.
"""

load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:java_library.bzl", "java_library")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_TWEAKS = ("EXTEND_RUNTIME_EXCEPTION",)

def _get_lang():
    return "java-swift"

def _get_names():
    return ("java-swift",)

def _get_compiler():
    return config.get_thrift_swift_compiler()

def _get_compiler_args(
        compiler_lang,
        flags,
        options,
        **_kwargs):
    """
    Return args to pass into the compiler when generating sources.
    """
    _ignore = compiler_lang
    _ignore = flags

    args = [
        "-tweak",
        "ADD_CLOSEABLE_INTERFACE",
    ]
    add_thrift_exception = True
    for option in options:
        if option == "T22418930_DO_NOT_USE_generate_beans":
            args.append("-generate_beans")
        elif option == "T22418930_DO_NOT_USE_unadd_thrift_exception":
            add_thrift_exception = False
        elif option in _TWEAKS:
            args.append("-tweak")
            args.append(option)
        else:
            fail('the "{}" java-swift option is invalid'.format(option))
    if add_thrift_exception:
        args.extend(["-tweak", "ADD_THRIFT_EXCEPTION"])
    return args

def _get_compiler_command(
        compiler,
        compiler_args,
        includes,
        additional_compiler):
    _ignore = additional_compiler

    cmd = []
    cmd.append("$(exe {})".format(compiler))
    cmd.append("-include_paths")
    cmd.append(
        "$(location {})".format(includes),
    )
    cmd.extend(compiler_args)
    cmd.append("-out")

    # We manually set gen-swift here for the purposes of following
    # the convention in the fbthrift generator
    cmd.append('"$OUT"{}'.format("/gen-swift"))
    cmd.append('"$SRCS"')
    return " ".join(cmd)

def _get_generated_sources(
        base_path,
        name,
        thrift_srcs,
        services,
        options,
        **_kwargs):
    # we want all the sources under gen-swift
    _ignore = base_path
    _ignore = name
    _ignore = thrift_srcs
    _ignore = services
    _ignore = options

    return {"": "gen-swift"}

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        java_swift_maven_coords = None,
        visibility = None,
        **_kwargs):
    _ignore = base_path
    _ignore = thrift_srcs

    out_srcs = []

    # Pack all generated source directories into a source zip, which we'll
    # feed into the Java library rule.
    if sources_map:
        src_zip_name = name + ".src.zip"
        fb_native.zip_file(
            name = src_zip_name,
            labels = ["generated"],
            visibility = visibility,
            srcs = [
                source
                for sources in sources_map.values()
                for source in sources.values()
            ],
            out = src_zip_name,
        )
        out_srcs.append(":" + src_zip_name)

    out_deps = []
    out_deps.extend(deps)
    out_deps.append("//third-party-java/com.google.guava:guava")
    out_deps.append("//third-party-java/org.apache.thrift:libthrift")
    out_deps.append(
        "//third-party-java/com.facebook.swift:swift-annotations",
    )

    maven_publisher_enabled = False
    if java_swift_maven_coords != None:
        maven_publisher_enabled = False  # TODO(T34003348)
        expected_coords_prefix = "com.facebook.thrift:"
        if not java_swift_maven_coords.startswith(expected_coords_prefix):
            fail(
                "java_swift_maven_coords must start with '{}'".format(expected_coords_prefix),
            )
        expected_options = sets.make(("EXTEND_RUNTIME_EXCEPTION",))
        if not sets.is_equal(sets.make(options), expected_options):
            fail((
                "When java_swift_maven_coords is specified, you must set" +
                " thrift_java_swift_options = {}"
            ).format(sets.to_list(expected_options)))

    java_library(
        name = name,
        visibility = visibility,
        srcs = out_srcs,
        duplicate_finder_enabled_DO_NOT_USE = False,
        exported_deps = out_deps,
        maven_coords = java_swift_maven_coords,
        maven_publisher_enabled = maven_publisher_enabled,
    )

swift_thrift_converter = thrift_interface.make(
    get_compiler = _get_compiler,
    get_compiler_args = _get_compiler_args,
    get_compiler_command = _get_compiler_command,
    get_generated_sources = _get_generated_sources,
    get_lang = _get_lang,
    get_language_rule = _get_language_rule,
    get_names = _get_names,
)
