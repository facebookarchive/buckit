load("@fbcode_macros//build_defs:config.bzl", "config")

def require_global_compiler(msg, compiler = None):
    """
    Assert that a global compiler is set.
    """

    global_compiler = config.get_global_compiler_family()
    if compiler == None:
        if global_compiler == None:
            fail(msg)
    elif global_compiler != compiler:
        fail(msg)
