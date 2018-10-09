"""
Helpers to related to C/C++ compiler families used for the build.
"""

load("@fbcode_macros//build_defs:build_mode.bzl", "build_mode")
load("@fbcode_macros//build_defs:config.bzl", "config")

def _get_supported_compilers():
    """
    Return list of compilers supported in this build mode.
    """

    # If a global compiler is set, then always return a list of just that.
    global_compiler_family = config.get_global_compiler_family()
    if global_compiler_family:
        return [global_compiler_family]

    # Otherwise, we assume we support clang and gcc.
    return ["clang", "gcc"]

def _require_global_compiler(msg, compiler = None):
    """
    Assert that a global compiler is set.
    """

    global_compiler = config.get_global_compiler_family()
    if compiler == None:
        if global_compiler == None:
            fail(msg)
    elif global_compiler != compiler:
        fail(msg)

def _get_compiler_for_base_path(base_path, override_compiler = None):
    """
    Return the compiler family to use for the buildfile at the given base path.
    """

    # Get the configured global and default compilers.
    global_compiler = config.get_global_compiler_family()
    default_compiler = config.get_default_compiler_family()

    # Grab the compiler set in the BUILD_MODE file.
    mode = build_mode.get_build_mode_for_base_path(base_path)
    mode_compiler = mode.compiler if mode != None else None

    # If a global compiler is set, use that.
    # T34130018: Even if a BUILD_MODE file or cpp_binary rule attempts to set a
    # different compiler than the global compiler set by the build mode, we use
    # the global compiler, silently ignoring the BUILD MODE or cpp_binary rule
    # setting.
    if global_compiler != None:
        return global_compiler

    # The next highest priority override is the override_compiler that may be
    # set by the cpp_binary rule's compiler_overrides map.
    if override_compiler != None:
        return override_compiler

    # Next, use the compiler set in the BUILD_MODE file.
    if mode_compiler != None:
        return mode_compiler

    # Lastly, fallback to the default.
    return default_compiler

def _get_compiler_for_current_buildfile(override_compiler = None):
    return _get_compiler_for_base_path(
        native.package_name(),
        override_compiler = override_compiler,
    )

compiler = struct(
    get_compiler_for_base_path = _get_compiler_for_base_path,
    get_compiler_for_current_buildfile = _get_compiler_for_current_buildfile,
    get_supported_compilers = _get_supported_compilers,
    require_global_compiler = _require_global_compiler,
)
