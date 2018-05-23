# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
#

"""
Various helpers to get labels for use in third-party
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:paths_config.bzl", "paths_config")

def _third_party_target(platform, project, rule):
    """
    Get a third-party target

    Args:
        platform: The "platform" that is being built for (e.g. gcc-5)
                  This is not the host architecture or OS, it is (potentially)
                  used in path creation
        project: The name of the project that is being referenced
        rule: The name of the rule inside of the project's build file

    Returns:
        The target for the args. This is something like
        //third-party-buck/<platform>/build/<project>:<rule> at Facebook,
        and something like <project>//<project>:<rule> in OSS
    """
    if paths_config.use_platforms_and_build_subdirs:
        return "//{}:{}".format(
            paths.join(
                paths_config.third_party_root,
                platform,
                "build",
                project,
            ),
            rule,
        )
    else:
        # For OSS compatibility
        return "{}//{}:{}".format(project, project, rule)

def _external_dep_target(raw_target, platform, lang_suffix = ""):
    """
    Take one of the various external dependency formats, and return a target

    Args:
        raw_target: This is one of several formats (kept mostly for legacy
                    reasons)
                        - "<project>": Use a rule named <project> inside of
                            <project>. e.g. "curl"
                        - (<project>,): Works the same as the raw string
                        - (<project>, <version>)
                            Gets a specific target and version. This is mostly
                            legacy behavior, as explicit version support hacks
                            were factored outsome time ago
                        - (<project>, <version>, <rule>)
                            This is the normal style of external deps (where
                            <version> is None). This will select a specific
                            rule inside of the project's resolved build file.
        platform: The name of a platform that will be potentially used in the
                  target path (e.g. gcc-5-glibc2.23). This is discarded in OSS
        lang_suffix: If provided, this will be appended for rules that do not
                     explicitly specify a rule (i.e. the first three types of
                     arguments mentioned above)

    Returns:
        A normalized target for the specified platform, project and rule
    """

    # We allow both tuples, and strings for legacy reasons
    if type(raw_target) == type(()):
        target = raw_target
    elif type(raw_target) == type(""):
        target = (raw_target,)
    else:
        fail("external dependency should be a tuple or string, " +
             "not {}".format(raw_target))

    if len(target) in (1, 2):
        project = target[0]
        rule = target[0] + lang_suffix

    elif len(target) == 3:
        project = target[0]
        rule = target[2]

    else:
        fail(("illegal external dependency {}: must have 1, 2, or 3 elements").format(raw_target))

    return _third_party_target(platform, project, rule)

third_party = struct(
    external_dep_target = _external_dep_target,
    third_party_target = _third_party_target,
)
