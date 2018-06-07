"""
A set of configurations for various path operations. This is mostly to
reconcile internal Facebook path resolution methods with open source-friendly
strategies
"""
paths_config = struct(
    # The root directory for third-party packages in a monorepo
    third_party_root="",
    # Whether //<third-party-root>/<platform>/build is the prefix to use for
    # third-party packages
    use_platforms_and_build_subdirs=False,
)
