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

_CORE_TOOLS_PATH = read_config('fbcode', 'core_tools_path')
_CORE_TOOLS = None


def is_core_tool(base_path, name):
    """
    Returns whether the target represented by the given base path and name is
    considered a "core" tool.
    """

    global _CORE_TOOLS, _CORE_TOOLS_PATH

    # Outside of fbcode, the rulekey thrash should not exist, so skip
    # in all cases
    if not _CORE_TOOLS_PATH:
        return False

    # Load core tools from the path, if it hasn't been already.
    if _CORE_TOOLS is None:
        add_build_file_dep('//' + _CORE_TOOLS_PATH)
        tools = set()
        with open(_CORE_TOOLS_PATH) as of:
            for line in of:
                if not line.startswith('#'):
                    tools.add(line.strip())
        _CORE_TOOLS = tools

    target = '//{}:{}'.format(base_path, name)
    return target in _CORE_TOOLS
