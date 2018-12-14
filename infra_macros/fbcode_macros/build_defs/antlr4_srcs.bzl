load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def antlr4_srcs(name, srcs, visibility = None):
    """
    Generates a zip file that contains antlr4 srcs from java sources

    Outputs:
        {name}: The main zip rule
        {name}_generated_srcs: The rule that invokes antlr

    Args:
        name: The name of the rule
        srcs: A list of sources to send to antlr4
        visibility: The rule's visibility
    """
    visibility = get_visibility(visibility, name)

    generated_srcs_rule_name = name + "_generated_srcs"

    fb_native.genrule(
        name = generated_srcs_rule_name,
        out = "antlr4_srcs",
        srcs = srcs,
        cmd = "java -cp $(classpath //third-party-java/org.antlr:antlr4) org.antlr.v4.Tool -o $OUT $SRCS",
        visibility = visibility,
    )
    fb_native.zip_file(
        name = name,
        srcs = [":" + generated_srcs_rule_name],
        out = name + ".src.zip",
        visibility = visibility,
    )
