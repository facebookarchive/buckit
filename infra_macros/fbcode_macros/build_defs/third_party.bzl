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
load("@fbcode_macros//build_defs:default_platform.bzl", "get_default_platform")
load("@fbcode_macros//build_defs:rule_target_types.bzl", "rule_target_types")
load("@fbcode_macros//build_defs:third_party_config.bzl", "third_party_config")

_THIRD_PARTY_REPOS = rule_target_types.THIRD_PARTY_REPOS

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

def _get_build_path(platform):
    """ Get the path to a `build` directory for a given platform """
    if paths_config.use_platforms_and_build_subdirs:
        return paths.join(paths_config.third_party_root, platform, "build")
    else:
        return paths_config.third_party_root

def _get_build_target_prefix(platform):
    """
    Returns the first part of a target that would be in the build directory for a given platform

    Args:
        platform: The platform to search for

    Returns:
        The first part of the target, e.g. //third-party/build/
    """
    return "//{}/".format(_get_build_path(platform))

def _get_tools_target_prefix(platform):
    """
    Returns the first part of a target that would be in the tools directory for a given platform

    Args:
        platform: The platform to search for

    Returns:
        The first part of the target, e.g. //third-party/tools/
    """
    return "//{}/".format(_get_tools_path(platform))

def _get_tools_path(platform):
    """ Get the path to a `tools` directory for a given platform """
    if paths_config.use_platforms_and_build_subdirs:
        return paths.join(paths_config.third_party_root, platform, "tools")
    else:
        return paths_config.third_party_root

def _get_tool_path(project, platform):
    """ Get the path to a `tool` directory for a given project """
    if paths_config.use_platforms_and_build_subdirs:
        return paths.join(paths_config.third_party_root, platform, "tools", project)
    else:
        return paths.join(paths_config.third_party_root, project)

def _get_tool_target(project, subpath, target_name, platform):
    """ Gets the target a rule in a project's `tool` directory """
    if paths_config.use_platforms_and_build_subdirs:
        subpath_fragment = "/" + subpath if subpath else ""
        return "//{}/{}/tools/{}{}:{}".format(
            paths_config.third_party_root,
            platform,
            project,
            subpath_fragment,
            target_name,
        )
    else:
        return "{}//{}:{}".format(project, subpath, target_name)

def _get_tool_bin_target(project, platform):
    """
    The the "bin" target for a given project and platform.

    This is the main target for a tool, like gcc or thrift
    """
    if paths_config.use_platforms_and_build_subdirs:
        return "//{}/{}/tools:{}/bin".format(
            paths_config.third_party_root,
            platform,
            project,
        )
    else:
        return "{}//{}:{}".format(project, project, project)

def _replace_third_party_repo_list(targets, platform):
    """
    Converts a list of targets potentially containing @/third-party to buck-compatible targets for the given platform

    Args:
        targets: A list of targets potentially containing @/third-party: to
                 convert into platform-normalized, buck-compatible targets
        platform: The platform to use. If not specified, auto-detection based
                  on the calling build file will be attempted

    Returns:
        A list of strings with @/third-party: properly replaced
    """
    return [_replace_third_party_repo(target, platform) for target in targets]

def _replace_third_party_repo(string, platform):
    """
    Converts the @/third-party: string to the appropriate platform target prefix

    This is to allow support of @/third-party: as a way to specify the
    path within third-party for the specified platform. As platform support
    improves in buck, this will be removed

    Args:
        string: The string to in which to replace @/third-party:. e.g.
                @/third-party:zstd:bin/zstdcat might become
                //third-party-buck/build/<platform>/zstd:bin/zstdcat
        platform: The platform to use. If not specified, auto-detection based
                  on the calling build file will be attempted

    Returns:
        The original string with @/third-party: properly replaced
    """

    # TODO: OSS
    if platform == None:
        platform = get_default_platform()
    return string.replace(
        "@/third-party-tools:",
        _get_tools_target_prefix(platform),
    ).replace(
        "@/third-party:",
        _get_build_target_prefix(platform),
    )

def _get_third_party_config_for_platform(platform):
    """ Returns the raw third party configuration for a specific platform """
    return third_party_config["platforms"][platform]

def _is_tp2_target(target):
    """
    Determines whether or not this is a special 'third-party' or 'third-party tools'
    target. This can be used to modify final buck labels in various conversion methods

    Args:
      target: A `RuleTarget` object
    """
    return target.repo in _THIRD_PARTY_REPOS

def _is_tp2(base_path):
    """
    Return whether the rule this `base_path` corresponds to came from third-party.
    """

    return base_path.startswith("third-party-buck/")

def _is_tp2_src_dep(src):  # type: Union[str, RuleTaret] -> bool
    """
    Return whether the given source path refers to a tp2 target.
    """
    return getattr(src, "repo", None) in _THIRD_PARTY_REPOS

# The short name of the implicit TP2 project target.
_TP2_PROJECT_TARGET_NAME = "__project__"

def _get_tp2_project_name(base_path):
    """
    Return the name of the TP2 project at the given base path.
    """

    # third-party-buck/platform/{build,tools}/<project>
    return base_path.split("/")[3]

def _get_tp2_project_target(project):
    """
    Return a RuleTarget for the given TP2 project
    """
    return rule_target_types.ThirdPartyRuleTarget(project, _TP2_PROJECT_TARGET_NAME)

def _get_tp2_platform(base_path):
    """
    Get the TP2 platform based on the package

    Args:
        base_path: The package that the build file is in

    Returns:
        The fbcode platform as a string
    """

    # third-party-buck/<platform>/{build,tools}/<project>
    return base_path.split("/")[1]

third_party = struct(
    external_dep_target = _external_dep_target,
    get_build_path = _get_build_path,
    get_build_target_prefix = _get_build_target_prefix,
    get_third_party_config_for_platform = _get_third_party_config_for_platform,
    get_tool_bin_target = _get_tool_bin_target,
    get_tool_path = _get_tool_path,
    get_tool_target = _get_tool_target,
    get_tools_path = _get_tools_path,
    get_tp2_platform = _get_tp2_platform,
    get_tp2_project_name = _get_tp2_project_name,
    get_tp2_project_target = _get_tp2_project_target,
    is_tp2 = _is_tp2,
    is_tp2_src_dep = _is_tp2_src_dep,
    is_tp2_target = _is_tp2_target,
    replace_third_party_repo = _replace_third_party_repo,
    replace_third_party_repo_list = _replace_third_party_repo_list,
    third_party_target = _third_party_target,
)
