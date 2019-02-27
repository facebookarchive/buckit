def nspawn_in_subvol_args(layer):
    cpp_lib = native.read_config("defaults.cxx_library", "type")
    python_pkg = native.read_config("python", "package_style")

    # Some Buck modes build non-portable artifacts that MUST be executed out
    # of the original repo.
    requires_repo = (cpp_lib == "shared" or python_pkg == "inplace")
    return ["--layer", "$(location {})".format(layer)] + (
        ["--bind-repo-ro"] if requires_repo else []
    )
