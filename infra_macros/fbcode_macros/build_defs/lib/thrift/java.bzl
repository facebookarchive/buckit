"""
Specializer to support generating Java libraries from thrift sources
using plain fbthrift or Apache Thrift.
"""

load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:java_library.bzl", "java_library")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_DEPRECATED_RUNTIME_DEPENDENCIES = [
    "//thrift/lib/java:thrift",
    "//third-party-java/org.slf4j:slf4j-api",
]

_DEPRECATED_APACHE_RUNTIME_DEPENDENCIES = [
    "//third-party-java/org.apache.thrift:libthrift",
    "//third-party-java/org.slf4j:slf4j-api",
]

def _deprecated_get_compiler_command(
        compiler,
        compiler_args,
        includes,
        additional_compiler):
    check_cmd = "$(exe //tools/build/buck/java:check_thrift_flavor) fb $SRCS"
    base_compiler_command = thrift_interface.default_get_compiler_command(
        compiler,
        compiler_args,
        includes,
        additional_compiler,
    )
    return "{} && {}".format(check_cmd, base_compiler_command)

def _deprecated_get_compiler():
    return native.read_config("thrift", "compiler", thrift_interface.default_get_compiler())

def _deprecated_get_compiler_lang():
    return "java"

def _deprecated_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = thrift_src
    _ignore = services
    _ignore = options

    # We want *all* the generated sources, so top-level directory.
    return {"": "gen-java"}

def _deprecated_get_lang():
    return "javadeprecated"

def _deprecated_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        javadeprecated_maven_coords = None,
        javadeprecated_maven_publisher_enabled = False,
        javadeprecated_maven_publisher_version_prefix = "1.0",
        visibility = None,
        _runtime_dependencies = _DEPRECATED_RUNTIME_DEPENDENCIES,
        **_kwargs):
    _ignore = base_path
    _ignore = thrift_srcs
    _ignore = options

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

    # Wrap the source zip in a java library rule, with an implicit dep on
    # the thrift library.
    out_deps = []
    out_deps.extend(deps)
    out_deps.extend(_runtime_dependencies)
    java_library(
        name = name,
        srcs = out_srcs,
        duplicate_finder_enabled_DO_NOT_USE = False,
        exported_deps = out_deps,
        maven_coords = javadeprecated_maven_coords,
        maven_publisher_enabled = javadeprecated_maven_publisher_enabled,
        maven_publisher_version_prefix = (
            javadeprecated_maven_publisher_version_prefix
        ),
        visibility = visibility,
    )

def _deprecated_get_names():
    return ("javadeprecated",)

def _deprecated_apache_get_compiler_command(
        compiler,
        compiler_args,
        includes,
        additional_compiler):
    _ignore = additional_compiler

    check_cmd = "$(exe //tools/build/buck/java:check_thrift_flavor) apache $SRCS"

    cmd = []
    cmd.append("$(exe {})".format(compiler))
    cmd.extend(compiler_args)
    cmd.append("-I")
    cmd.append(
        "$(location {})".format(includes),
    )
    cmd.append("-o")
    cmd.append('"$OUT"')
    cmd.append('"$SRCS"')

    return check_cmd + " && " + " ".join(cmd)

def _deprecated_apache_get_compiler():
    return config.get_thrift_deprecated_apache_compiler()

def _deprecated_apache_get_lang():
    return "javadeprecated-apache"

def _deprecated_apache_get_names():
    return ("javadeprecated-apache",)

def _deprecated_apache_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        javadeprecated_maven_coords = None,
        javadeprecated_maven_publisher_enabled = False,
        javadeprecated_maven_publisher_version_prefix = "1.0",
        visibility = None,
        _runtime_dependencies = _DEPRECATED_RUNTIME_DEPENDENCIES,
        **kwargs):
    _deprecated_get_language_rule(
        base_path = base_path,
        name = name,
        thrift_srcs = thrift_srcs,
        options = options,
        sources_map = sources_map,
        deps = deps,
        javadeprecated_maven_coords = javadeprecated_maven_coords,
        javadeprecated_maven_publisher_enabled = javadeprecated_maven_publisher_enabled,
        javadeprecated_maven_publisher_version_prefix = javadeprecated_maven_publisher_version_prefix,
        visibility = visibility,
        _runtime_dependencies = _DEPRECATED_APACHE_RUNTIME_DEPENDENCIES,
        **kwargs
    )

java_deprecated_thrift_converter = thrift_interface.make(
    get_compiler = _deprecated_get_compiler,
    get_compiler_command = _deprecated_get_compiler_command,
    get_compiler_lang = _deprecated_get_compiler_lang,
    get_generated_sources = _deprecated_get_generated_sources,
    get_lang = _deprecated_get_lang,
    get_language_rule = _deprecated_get_language_rule,
    get_names = _deprecated_get_names,
)

java_deprecated_apache_thrift_converter = thrift_interface.make(
    get_compiler = _deprecated_apache_get_compiler,
    get_compiler_command = _deprecated_apache_get_compiler_command,
    get_compiler_lang = _deprecated_get_compiler_lang,
    get_generated_sources = _deprecated_get_generated_sources,
    get_lang = _deprecated_apache_get_lang,
    get_language_rule = _deprecated_apache_get_language_rule,
    get_names = _deprecated_apache_get_names,
)
