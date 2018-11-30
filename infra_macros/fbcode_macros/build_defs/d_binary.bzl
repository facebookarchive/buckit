load("@fbcode_macros//build_defs:d_common.bzl", "d_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def d_binary(
        name,
        srcs = (),
        deps = (),
        linker_flags = (),
        external_deps = (),
        visibility = None):
    """
    A thin wrapper over buck's native d_binary rule

    Args:
        name: The name of the rule
        srcs: A collection of source files / targets
        deps: A sequence of dependencies for the rule
        external_deps: A sequence of tuples of third-party dependencies to use
        linker_flags: Additional flags that hsould be passed to the linker
        visbiility: The visibility of this rule. This may be modified by common configuration
    """

    attrs = d_common.convert_d(
        name = name,
        is_binary = True,
        d_rule_type = "d_binary",
        srcs = srcs,
        deps = deps,
        linker_flags = linker_flags,
        external_deps = external_deps,
        visibility = visibility,
    )
    fb_native.d_binary(**attrs)
