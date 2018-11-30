load("@fbcode_macros//build_defs:d_common.bzl", "d_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def d_unittest(
        name,
        srcs = (),
        deps = (),
        tags = (),
        linker_flags = (),
        external_deps = (),
        visibility = None):
    """
    A thin wrapper over buck's native d_test rule

    Args:
        name: The name of the rule
        srcs: A collection of source files / targets
        deps: A sequence of dependencies for the rule
        external_deps: A sequence of tuples of third-party dependencies to use
        tags: A sequence of arbitary strings to attach to unittest rules. Non test rules
              should use 'None' for non-test rules.
        linker_flags: Additional flags that hsould be passed to the linker
        visbiility: The visibility of this rule. This may be modified by common configuration
    """

    attrs = d_common.convert_d(
        name = name,
        is_binary = True,
        d_rule_type = "d_unittest",
        srcs = srcs,
        deps = deps,
        tags = tags,
        linker_flags = linker_flags,
        external_deps = external_deps,
        visibility = visibility,
    )
    fb_native.d_test(**attrs)
