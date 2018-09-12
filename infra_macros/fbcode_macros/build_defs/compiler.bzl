"""
Helpers to related to C/C++ compiler families used for the build.
"""

load("@fbcode_macros//build_defs:build_mode.bzl", "build_mode")
load("@fbcode_macros//build_defs:config.bzl", "config")

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

def _get_compiler_for_base_path(base_path):
    """
    Return the compiler family to use for the buildfile at the given base path.
    """

    # Get the configured global and default compilers.
    global_compiler = config.get_global_compiler_family()
    default_compiler = config.get_default_compiler_family()

    # Grab the compiler set in the BUILD_MODE file.
    mode = build_mode.get_build_mode_for_base_path(base_path)
    mode_compiler = mode.compiler if mode != None else None

    if (mode_compiler != None and
        global_compiler != None and
        mode_compiler != global_compiler):
        fail("BUILD_MODE file trying to override fixed global compiler")

    # If a global compiler is set, use that.
    if global_compiler != None:
        return global_compiler

    # Next, use the compiler set in the BUILD_MODE file.
    if mode_compiler != None:
        return mode_compiler

    # Lastly, fallback to the default.
    return default_compiler

def _get_compiler_for_current_buildfile():
    return _get_compiler_for_base_path(native.package_name())

compiler = struct(
    get_compiler_for_base_path = _get_compiler_for_base_path,
    get_compiler_for_current_buildfile = _get_compiler_for_current_buildfile,
    require_global_compiler = _require_global_compiler,
)
