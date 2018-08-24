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
