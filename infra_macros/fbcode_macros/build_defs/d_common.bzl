load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")

def _get_platform():
    return native.read_config("d", "platform", None)

def _convert_d(
        name,
        is_binary,
        d_rule_type,
        srcs = (),
        deps = (),
        tags = None,
        linker_flags = (),
        external_deps = (),
        visibility = None):
    """
    Common logic for creating D rules

    Args:
        name: The name of the rule
        is_binary: Whether or not the rule is a binary rule. This impacts build info
                   and what is linked into the final binary
        d_rule_type: The name of the rule calling `convert_d`. This is used for build
                     information and other metadata
        srcs: A collection of source files / targets
        deps: A sequence of dependencies for the rule
        external_deps: A sequence of tuples of third-party dependencies to use
        tags: A sequence of arbitary strings to attach to unittest rules. Non test rules
              should use 'None' for non-test rules.
        linker_flags: Additional flags that hsould be passed to the linker
        visbiility: The visibility of this rule. This may be modified by common configuration

    Returns:
        A dictionary of kwargs that can be passed to a native buck rule
    """
    base_path = native.package_name()
    platform = _get_platform()
    visibility = get_visibility(visibility, name)

    attributes = {}

    attributes["name"] = name
    attributes["visibility"] = visibility
    attributes["srcs"] = srcs

    if tags != None:
        attributes["labels"] = label_utils.convert_labels(platform, "d", *tags)

    # Add in the base ldflags.
    out_ldflags = []
    out_ldflags.extend(linker_flags)
    out_ldflags.extend(
        cpp_common.get_ldflags(
            base_path,
            name,
            d_rule_type,
            binary = is_binary,
            build_info = is_binary,
            platform = platform if is_binary else None,
        ),
    )
    attributes["linker_flags"] = out_ldflags

    dependencies = []
    for target in deps:
        dependencies.append(
            src_and_dep_helpers.convert_build_target(
                base_path,
                target,
                platform = platform,
            ),
        )
    for target in external_deps:
        dependencies.append(
            src_and_dep_helpers.convert_external_build_target(target, platform = platform),
        )

    # All D rules get an implicit dep on the runtime.
    dependencies.append(
        target_utils.target_to_label(
            target_utils.ThirdPartyRuleTarget("dlang", "druntime"),
            platform = platform,
        ),
    )
    dependencies.append(
        target_utils.target_to_label(
            target_utils.ThirdPartyRuleTarget("dlang", "phobos"),
            platform = platform,
        ),
    )

    # Add in binary-specific link deps.
    if is_binary:
        dependencies.extend(
            src_and_dep_helpers.format_deps(
                cpp_common.get_binary_link_deps(
                    base_path,
                    name,
                    attributes["linker_flags"],
                ),
                platform = platform,
            ),
        )
    attributes["deps"] = dependencies

    return attributes

d_common = struct(
    convert_d = _convert_d,
)
