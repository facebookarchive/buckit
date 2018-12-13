# Copyright 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Common infrastructure for managing Python flavors and versions in third-party2.

"""

load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")

_TP2_PYTHON_PROJECT = third_party.get_tp2_project_target("python")

def _get_tp2_project_versions(project, platform):
    """
    Return a list of configured versions for given `project` on `platform`.

    Multiple versions of a TP2 project is only allowed for a small subset of
    projects (see `WHITELISTED_VERSIONED_PROJECTS` in `buckify_tp2.py`).
    """
    tp2_conf = third_party.get_third_party_config_for_platform(platform)
    vers = tp2_conf["build"]["projects"][project]
    if type(vers) == type(""):
        return [vers]
    res = []
    for ver in vers:
        # Each element is either a string, or a pair of the form
        # (ORIGINAL_TP2_VERSION, ACTUAL_VERSION):
        if type(ver) == type(""):
            res.append(ver)
        else:
            res.append(ver[1])
    return res

def _get_all_versions(platform):
    """
    Return a list of all configured Python versions for `platform`.
    """
    return _get_tp2_project_versions("python", platform)

def _add_flavored_versions(versioned_resources):
    """
    For each resource entry in `versioned_resources` that declares a Python
    version, add a corresponding entry for every configured TP2 Python version
    that subsumes the declared Python version.

    Args:
        versioned_resources: A list of versioned resource entries accepted by
                             Buck. Each entry in the list should be a pair of
                             the form
                             (
                                {
                                    LABEL1 : VERSION1,
                                    ...
                                    LABELn : VERSIONn
                                },
                                {
                                    SRC_FILE1 : DST_FILE1,
                                    ...
                                    SRC_FILEm : DST_FILEm
                                }
                             )
                             where LABELs are strings that identify dependency
                             targets, and VERSIONs are strings that specify the
                             required version of LABEL. Can be None.

    Returns:
        If `versioned_resources` is a list, then a copy of `versioned_resources`
        extended with entries for Python flavors. Otherwise,
        `versioned_resources` itself.
    """

    if type(versioned_resources) != type([]):
        return versioned_resources

    platforms = platform_utils.get_platforms_for_host_architecture()
    res = list(versioned_resources)
    for p in platforms:
        label = target_utils.target_to_label(_TP2_PYTHON_PROJECT, p)
        for version_spec, resource_spec in versioned_resources:
            if label in version_spec:
                pyver = version_spec[label]
                for cver in _get_all_versions(p):
                    # Simple flavor subsumption rule -- version A subsumes
                    # version B if B is a proper suffix of A:
                    if cver != pyver and cver.endswith(pyver):
                        new_spec = dict(version_spec)
                        new_spec[label] = cver
                        res.append([new_spec, resource_spec])
    return res

_PythonVersion = provider(fields = [
    "version_string",
    "flavor",
    "major",
    "minor",
    "patchlevel",
])

def _parse_python_version(version_string):
    if not version_string:
        fail("Empty version string provided")
    version_pieces = version_string.split(".")
    start_idx = 0
    flavor = ""
    if not version_pieces[0].isdigit():
        flavor = version_pieces[0]
        start_idx = 1
        if len(version_pieces) == 1:
            fail("Invalid version string {} provided".format(version_string))
    major = int(version_pieces[start_idx])
    minor = int(version_pieces[start_idx + 1]) if start_idx + 1 < len(version_pieces) else 0
    patchlevel = int(version_pieces[start_idx + 2]) if start_idx + 2 < len(version_pieces) else 0
    return _PythonVersion(
        version_string = version_string,
        flavor = flavor,
        major = major,
        minor = minor,
        patchlevel = patchlevel,
    )

# Versions selected based on most commonly specified version strings
_INTERNED_PYTHON_VERSIONS = {
    "2": _parse_python_version("2"),
    "2.6": _parse_python_version("2.6"),
    "2.7": _parse_python_version("2.7"),
    "3": _parse_python_version("3"),
    "3.0": _parse_python_version("3.0"),
    "3.2": _parse_python_version("3.2"),
    "3.3": _parse_python_version("3.3"),
    "3.4": _parse_python_version("3.4"),
    "3.5": _parse_python_version("3.5"),
    "3.6": _parse_python_version("3.6"),
    "3.7": _parse_python_version("3.7"),
}

_DEFAULT_PYTHON_MAJOR_VERSION = "3"

def _python_version(version_string):
    """
    An abstraction of tp2/python version strings that supports flavor prefixes.

    See `get_python_platforms_config()` in `tools/build/buck/gen_modes.py` for
    the format of flavored version strings.

    Because these are immutable objects, they may also be cached instances

    Args:
        version_string: The aforementioned version string

    Returns:
        A struct with the 'version_string' (the raw string), 'flavor', 'major',
        'minor', and 'patchlevel'. Minor and patchlevel are 0 if they were not
        provided, though the 0 will not appear in the version string
    """
    version_string = version_string or _DEFAULT_PYTHON_MAJOR_VERSION
    interned = _INTERNED_PYTHON_VERSIONS.get(version_string)
    if interned:
        return interned
    return _parse_python_version(version_string)

def _version_supports_flavor(python_version, flavor):
    """ 
    Whether a `python_version` is compatible with a flavor
    """
    return python_version.flavor.endswith(flavor)

python_versioning = struct(
    add_flavored_versions = _add_flavored_versions,
    python_version = _python_version,
    version_supports_flavor = _version_supports_flavor,
)
