load("@bazel_skylib//lib:partial.bzl", "partial")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/facebook:python_wheel_overrides.bzl", "python_wheel_overrides")
load("@fbcode_macros//build_defs/lib:cxx_platform_info.bzl", "CxxPlatformInfo")
load("@fbcode_macros//build_defs/lib:rule_target_types.bzl", "rule_target_types")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:third_party_config.bzl", "third_party_config")

def _translate_target(fbcode_platform, tp_type, base, base_path, name):
    """
    Translate a `third-party//` or `third-party-tools//` target to an fbcode
    target pointing to the fbcode-platform-specific third-party2 root.
    """

    # Process PyFI overrides
    if python_wheel_overrides.should_use_overrides():
        if fbcode_platform in python_wheel_overrides.PYFI_SUPPORTED_PLATFORMS:
            target = python_wheel_overrides.PYFI_OVERRIDES.get(base_path)
            if target != None:
                return target

    # Redirect unsupported projects to an error rule.
    config = third_party_config["platforms"][fbcode_platform][tp_type]
    if (base_path not in config["projects"] and
        # Gross workaround to handle deprecated `auxiliary_versions`.
        base_path.rsplit("-")[0] not in config.get("auxiliary_versions", {})):
        return rule_target_types.RuleTarget(
            "fbcode",
            "third-party-buck/missing/{0}".format(base_path),
            name,
        )

    # Translate to the appropriate third-party-buck root.
    return rule_target_types.RuleTarget(
        "fbcode",
        paths.join(base, base_path),
        name,
    )

def _build_tp2_virtual_cells(fbcode_platform):
    """
    Build virtual cells mapping `third-party//` and third-party-tools//` to the
    tp2 platform-specific build and tools roots.
    """

    return {
        "third-party": partial.make(
            _translate_target,
            fbcode_platform,
            "build",
            third_party.get_build_path(fbcode_platform),
        ),
        "third-party-tools": partial.make(
            _translate_target,
            fbcode_platform,
            "tools",
            third_party.get_tools_path(fbcode_platform),
        ),
    }

# Memoize the per-fbcode-platform virtual cells for use in older code that
# hasn't moved over to using the `CxxPlatformInfo` objects.
_TP2_VIRTUAL_CELLS = {
    p: _build_tp2_virtual_cells(p)
    for p in third_party_config["platforms"]
}

def _build_platforms(platforms_config, virtual_cells = True):
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
                    virtual_cells = _TP2_VIRTUAL_CELLS[name] if virtual_cells else None,
                ),
            )

    return platforms

_PLATFORMS = _build_platforms(third_party_config["platforms"])

fbcode_cxx_platforms = struct(
    build_platforms = _build_platforms,  # visible for testing
    build_tp2_virtual_cells = _build_tp2_virtual_cells,  # visible for testing
    PLATFORMS = _PLATFORMS,
    TP2_VIRTUAL_CELLS = _TP2_VIRTUAL_CELLS,
)
