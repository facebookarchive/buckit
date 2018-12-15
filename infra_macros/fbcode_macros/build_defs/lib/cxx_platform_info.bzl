# Describes information for macros about C/C++ platform configured in Buck
# (either internally, or via `.buckconfig`).  This is the primary abstraction
# point for how the macros should handle multiple C/C++ platforms each
# supporting different configurations (e.g. JEMalloc, sanitizers, modules,
# TP2).
CxxPlatformInfo = provider(fields = [
    # A UI alias used to refer to the given platform.
    "alias",
    # The C/C++ compiler family (e.g. clang, gcc).
    "compiler_family",
    # The architecture that this platform can be built on.
    "host_arch",
    # The OS that this platform can be built on.
    "host_os",
    # Name Buck uses for this platform.
    "name",
    # The architecture this platform builds for.
    "target_arch",
    # The OS this platform builds for.
    "target_os",
    # A map of virtual cells to functions used to translate them to real
    # targets (e.g. how to translate `third-party//boost:boost` to
    # `fbcode//third-party-buck/platform007/build/boost:boost` for the
    # "platform007" fbcode toolchain).
    "virtual_cells",
])
