"""
Helpers to related to C/C++ compiler families used for the build.
"""

load("@fbcode_macros//build_defs:config.bzl", "config")

def _get_compiler_for_base_path(base_path):
    """
    Return the compiler family to use for the buildfile at the given base path.
    """

    # If a global compiler is set, use that.
    global_compiler = config.get_global_compiler_family()
    if global_compiler != None:
        return global_compiler

     # Otherwise fallback to the default.
    return config.get_default_compiler_family()

def _get_compiler_for_current_buildfile():
    return _get_compiler_for_base_path(native.package_name())

compiler = struct(
    get_compiler_for_base_path = _get_compiler_for_base_path,
    get_compiler_for_current_buildfile = _get_compiler_for_current_buildfile,
)
