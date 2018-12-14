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

def _get_all_versions_for_platform(platform):
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
        label = target_utils.target_to_label(_TP2_PYTHON_PROJECT, fbcode_platform = p)
        for version_spec, resource_spec in versioned_resources:
            if label in version_spec:
                pyver = version_spec[label]
                for cver in _get_all_versions_for_platform(p):
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

_PythonVersionConstraint = provider(fields = ["op", "version"])

def _constraint_lt(left, right, _check_minor):
    return (left.major, left.minor, left.patchlevel) < (right.major, right.minor, right.patchlevel)

def _constraint_lte(left, right, _check_minor):
    return (left.major, left.minor, left.patchlevel) <= (right.major, right.minor, right.patchlevel)

def _constraint_gt(left, right, _check_minor):
    return (left.major, left.minor, left.patchlevel) > (right.major, right.minor, right.patchlevel)

def _constraint_gte(left, right, _check_minor):
    return (left.major, left.minor, left.patchlevel) >= (right.major, right.minor, right.patchlevel)

def _constraint_eq(left, right, check_minor):
    return (
        (left.major, left.minor, 0 if check_minor else left.patchlevel) ==
        (right.major, right.minor, 0 if check_minor else right.patchlevel)
    )

def _constraint_partial_match(left, right, check_minor):
    return (left.major == right.major and (not check_minor or left.minor == right.minor))

def _parse_python_version_constraint(constraint_string):
    if constraint_string.startswith("<="):
        version_string = constraint_string[2:].lstrip()
        op = _constraint_lte
    elif constraint_string.startswith(">="):
        version_string = constraint_string[2:].lstrip()
        op = _constraint_gte
    elif constraint_string.startswith("<"):
        version_string = constraint_string[1:].lstrip()
        op = _constraint_lt
    elif constraint_string.startswith("="):
        version_string = constraint_string[1:].lstrip()
        op = _constraint_eq
    elif constraint_string.startswith(">"):
        version_string = constraint_string[1:].lstrip()
        op = _constraint_gt
    else:
        version_string = constraint_string
        op = _constraint_eq
    version = _python_version(version_string)
    return _PythonVersionConstraint(version = version, op = op)

def _intern_constraints():
    """ Create a map of our most common constraints so that we can pull from the cache more often """
    result = {
        operator + version: _parse_python_version_constraint(operator + version)
        for version in ["2", "2.7", "3", "3.6"]
        for operator in ["", "<", "<=", "=", ">=", ">"]
    }
    result.update({
        2: _PythonVersionConstraint(
            version = _python_version("2"),
            op = _constraint_partial_match,
        ),
        3: _PythonVersionConstraint(
            version = _python_version("3"),
            op = _constraint_partial_match,
        ),
        "2": _PythonVersionConstraint(
            version = _python_version("2"),
            op = _constraint_partial_match,
        ),
        "3": _PythonVersionConstraint(
            version = _python_version("3"),
            op = _constraint_partial_match,
        ),
    })
    return result

_INTERNED_VERSION_CONSTRAINTS = _intern_constraints()

def _python_version_constraint(constraint_string):
    """
    Parses and creates a struct that represents a 'version constraint'

    This implements the semantics of the `py_version` and `versioned_srcs`
    parameters of the 'python_xxx' rule types.

    Note that this method may make use of internal caches of immutable objects

    Args:
        constraint_string: A string like '<3', '=2.7', or '3'

    Returns:
        A `PythonVersionConstraint` with a comparison `op` and a `version` set
    """

    if not constraint_string:
        constraint_string = _DEFAULT_PYTHON_MAJOR_VERSION
    else:
        # There are some versions that use integers, make sure we pick those up
        constraint_string = str(constraint_string)

    if constraint_string in _INTERNED_VERSION_CONSTRAINTS:
        return _INTERNED_VERSION_CONSTRAINTS[constraint_string]
    return _parse_python_version_constraint(constraint_string)

def _constraint_matches(constraint, version, check_minor = False):
    """
    Whether or not a constraint matches a version

    Args:
        constraint: The result of a `python_version_constraint()` call
        version: The result of a `python_version()` call
        check_minor: If true, partial checks look at the minor in addition to the major
                     version. For raw constraints (e.g. '2.7'), only the first major
                     and minor versions will be checked. That is, '2.7.1' will match
                     the '2.7' constraint if check_minor is True

    Returns:
        Whether the version matches the constraint. Note that the matching effectively
        checks against triples in most cases, and does not behave identically to
        python distutils' LooseVersion
    """
    if not _version_supports_flavor(version, constraint.version.flavor):
        return False

    return constraint.op(version, constraint.version, check_minor)

def _normalize_constraint(constraint):
    """ 
    Normalizes `constraint` to be a `PythonVersionConstraint` object

    Returns:
        Either `constraint` if it is a `PythonVersionConstraint` struct, or parses
        the string/int into a constraint
    """
    if hasattr(constraint, "version") and hasattr(constraint, "op"):
        return constraint
    else:
        return _python_version_constraint(constraint)

_ALL_PYTHON_VERSIONS = {
    platform: [
        _python_version(version_string)
        for version_string in _get_all_versions_for_platform(platform)
    ]
    for platform in platform_utils.get_all_platforms()
}

def _get_all_versions(fbcode_platform = None):
    """
    Returns a list of `PythonVersion` instances corresponding to the active
    Python versions for the given `platform`. If `platform` is not
    specified, then return versions for all platforms.
    """

    versions = {}
    for p in platform_utils.get_platforms_for_host_architecture():
        if fbcode_platform != None and fbcode_platform != p:
            continue
        for version in _ALL_PYTHON_VERSIONS[p]:
            versions[version] = None
    return versions.keys()

def _get_default_version(platform, constraint, flavor = ""):
    """
    Returns a `PythonVersion` instance corresponding to the first Python
    version that satisfies `constraint` and `flavor` for the given
    `platform`.
    """
    constraint = _normalize_constraint(constraint)
    for version in _ALL_PYTHON_VERSIONS[platform]:
        if _constraint_matches(constraint, version) and _version_supports_flavor(version, flavor):
            return version
    return None

def _constraint_matches_major(constraint, version):
    """
    True if `constraint` can be satisfied by a Python version that is of major `version` on some active platform.

    Args:
        constraint: A constraint that should be satified (`PythonVersionConstraint` or str)
        version: An integer major version that must be met in addition to the constraint
    """
    constraint = python_versioning.normalize_constraint(constraint)
    for platform_version in _get_all_versions():
        if platform_version.major == version and _constraint_matches(constraint, platform_version):
            return True
    return False

def _platform_has_version(platform, version):
    """
    Whether Python `version` is configured for `platform`.

    Args:
        platform: The fbcode platform to investigate
        version: The `PythonVersion` to inspect

    Returns:
        Whether `version` is configured for `platform`
    """
    for platform_version in _ALL_PYTHON_VERSIONS[platform]:
        if version.version_string == platform_version.version_string:
            return True
    return False

python_versioning = struct(
    add_flavored_versions = _add_flavored_versions,
    constraint_matches_major = _constraint_matches_major,
    get_all_versions = _get_all_versions,
    get_default_version = _get_default_version,
    python_version = _python_version,
    version_supports_flavor = _version_supports_flavor,
    platform_has_version = _platform_has_version,
    python_version_constraint = _python_version_constraint,
    constraint_matches = _constraint_matches,
    normalize_constraint = _normalize_constraint,
)
