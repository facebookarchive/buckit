load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")

def _get_version_universe(python_version):
    """
    Get the version universe for a specific python version

    Args:
        python_version: A `PythonVersion` that the universe should be fetched for

    Returns:
        The first third-party version universe string that corresponds to the python version
    """
    return third_party.get_version_universe([("python", python_version.version_string)])

python_common = struct(
    get_version_universe = _get_version_universe,
)
