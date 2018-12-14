load("@fbcode_macros//build_defs/lib:cxx_platform_info.bzl", "CxxPlatformInfo")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:third_party_config.bzl", "third_party_config")

def _build_platforms(platforms_config):
    """
    Returns the list of fbcode-based C/C++ platforms.
    """

    platforms = []

    # TODO(agallagher): We should generate this list from
    # `fbcode/toold/build/gen_modes.py` to avoid code duplication.
    for name, info in sorted(platforms_config.items()):
        for compiler_family in compiler.COMPILERS:
            platforms.append(
                CxxPlatformInfo(
                    alias = name,
                    compiler_family = compiler_family,
                    host_arch = info["architecture"],
                    host_os = "linux",
                    name = "{}-{}".format(name, compiler_family),
                    target_arch = info["architecture"],
                    target_os = "linux",  # Should this be "fbcode"?
                ),
            )

    return platforms

_PLATFORMS = _build_platforms(third_party_config["platforms"])

fbcode_cxx_platforms = struct(
    build_platforms = _build_platforms,  # visible for testing
    PLATFORMS = _PLATFORMS,
)
