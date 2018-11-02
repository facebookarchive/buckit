# Copyright 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Common infrastructure for managing Python flavors and versions in third-party2.

"""

load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")

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

python_versioning = struct(
    add_flavored_versions = _add_flavored_versions,
)
