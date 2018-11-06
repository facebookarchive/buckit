"""
Enum of different autoheaders settings
"""

AutoHeaders = struct(
    NONE = "none",
    # Uses a recursive glob to resolve all transitive headers under the given
    # directory.
    RECURSIVE_GLOB = "recursive_glob",
    # Infer headers from sources of the rule.
    SOURCES = "sources",
)

def get_auto_headers(auto_headers):
    """
    Returns the level of auto-headers to apply to a rule

    Args:
        auto_headers: One of the values in `AutoHeaders`

    Returns:
        The value passed in as auto_headers, or the value from configuration if
        `auto_headers` is None
    """
    if auto_headers != None:
        return auto_headers
    return native.read_config("cxx", "auto_headers", AutoHeaders.SOURCES)
