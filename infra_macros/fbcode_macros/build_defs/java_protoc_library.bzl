load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")

def _java_protoc_compile_srcs(
        name,
        srcs,
        generated_src_zip_rule_name):
    cmd = (
        "include=; for s in `dirname $SRCS|sort|uniq`; do include=\"$include -I$s\"; done; " +
        "java -cp $(classpath //third-party-java/com.github.os72:protoc-jar) " +
        "com.github.os72.protocjar.Protoc -v3.5.0 --include_std_types --java_out=$OUT $include $SRCS"
    )

    fb_native.genrule(
        name = generated_src_zip_rule_name,
        srcs = srcs,
        out = name + ".src.zip",
        cmd = cmd,
    )

def _java_protoc_create_library(
        name,
        generated_src_zip_rule_name,
        visibility):
    fb_native.java_library(
        name = name,
        srcs = [":" + generated_src_zip_rule_name],
        exported_deps = ["//third-party-java/com.google.protobuf:protobuf-java"],
        visibility = get_visibility(visibility, name),
    )

def java_protoc_library(
        name,
        srcs,
        visibility = None):
    """
    Creates a java jar from protoc sources

    Args:
        name: The name of the main java_library rule to be created
        srcs: A list of protoc sources
        visibility: Visibility for the main java_ibrary rule
    """
    generated_src_zip_rule_name = name + "_src_zip"
    _java_protoc_compile_srcs(name, srcs, generated_src_zip_rule_name)
    _java_protoc_create_library(name, generated_src_zip_rule_name, visibility)
