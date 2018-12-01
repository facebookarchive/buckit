def _get_lua_base_module_parts(base_path, base_module):
    """
    Get a base module from either provided data, or from the base path of the package

    Args:
        base_path: The package path
        base_module: None, or a string representing the absence/presence of a base
                     module override

    Returns:
        Returns a list of parts of a base module based on base_path/base_module.
        If base_module is None, a default one is created based on package name.
    """

    # If base module is unset, prepare a default.
    if base_module == None:
        return ["fbcode"] + base_path.split("/")

        # If base module is empty, return the empty list.
    elif not base_module:
        return []

        # Otherwise, split it on the module separater.
    else:
        return base_module.split(".")

def _get_lua_base_module(base_path, base_module):
    parts = _get_lua_base_module_parts(base_path, base_module)
    return ".".join(parts)

def _get_lua_init_symbol(base_path, name, base_module):
    parts = _get_lua_base_module_parts(base_path, base_module)
    return "_".join(["luaopen"] + parts + [name])

lua_common = struct(
    get_lua_base_module = _get_lua_base_module,
    get_lua_init_symbol = _get_lua_init_symbol,
)
