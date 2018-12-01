"""
Helper functions for managing core tools in fbcode.

The concept of core tools is somewhat of a hack to enumerate binary rules which
are used as tools during the build, and so are transitive deps of several other
rules in the build.  It's useful to enumerate these to whitelist them from
certain operations that would otherwise transitively affect rule keys.  In a
future world where we differentiate between target and host platforms, we can
likely remove it.

For example, we mark fbcode's thrift compiler as a "core tool" to *prevent*
applying special linker flags to strip C/C++ debug info during sandcastle
builds, which would cause the rule key of the thrift compiler to change, which
would then transitively change the rule keys of all C/C++ objects built from
generated thrift sources, causing the vast majority of sandcastle and developer
builds to diverge.
"""

load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@fbcode_macros//build_defs:core_tools_targets.bzl", "core_tools_targets")

def _is_core_tool(package_name, name):
    """
    Returns whether the target represented by the given package name and rule name is considered a "core" tool.

    Args:
        package_name: The name of the package (without any leading //)
        name: The name of the rule to inspect

    Returns:
        Whether the target is a core tool
    """
    return sets.contains(core_tools_targets, (package_name, name))

core_tools = struct(
    is_core_tool = _is_core_tool,
)
