load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:rule_target_types.bzl", "rule_target_types")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbsource//tools/build_defs:translate_to_fbsource_paths.bzl", "MISSING_CELL")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_string", "is_tuple", "is_unicode")

# Re-export from rule_target_types so that the common case usage is to use target_utils,
# but having a separate 'types' file allows us to break a few cyclic dependencies down
# the road (e.g. on "third-party" when we're doing some of the path resolution in
# to_label() and the like

def _convert_missing_cell(repo, base):
    """Converts references to MISSING_CELL to fbsource-relative paths

    fbcode has a handful of references to the other cells in fbsource (mostly
    xplat), so this function is to ensure that those references survive the
    removal of those cells (see: https://fburl.com/mobile-unification).
    """
    if MISSING_CELL == None or repo != MISSING_CELL:
        return (repo, base)
    else:
        return ("fbsource", "{}/{}".format(MISSING_CELL, base))

def _parse_target(target, default_repo = None, default_base_path = None):
    """
    Parse a target string into a RuleTarget struct

    Args:
        target: A string like '//foo:bar', ':bar', 'xplat//foo:bar',
                '@/third-party:foo:bar', or '@/third-party-tools:foo:bar'
        default_repo: If provided, this repo will be used in the RuleTarget if one
                      could not be parsed out of the target
        default_base_path: The package to use for base_path if none was provided. e.g.
                           a target of ':bar', with a default_base_path of 'foo' would
                           yield a target that could be written as '//foo:bar'

    Returns:
        A `RuleTarget` struct from the parsed target
    """
    if target.startswith("@/third-party"):
        normalized = target[2:]
    elif target.startswith(":"):
        normalized = target
    elif "//" in target and ":" in target:
        # We have a full buck rule. Ignore the default repo and default
        # base path. The default repo and base path are only used in the case of
        # `:foo` targets, and they won't hit this branch
        repo, base = target.split("//", 1)
        repo = repo or default_repo
        base, name = base.split(":", 1)

        # TODO(T31640489): Remove this extra step
        repo, base = _convert_missing_cell(repo, base)
        return rule_target_types.RuleTarget(repo, base, name)
    else:
        fail('rule name must contain "//" (when absolute) or ":" (when relative): "{}"'.format(target))

    # Split the target into a package and a name
    parts = normalized.split(":")

    if len(parts) < 2:
        fail('rule name must contain at least one ":" character: "{}"'.format(target))
    elif len(parts) == 2:
        repo = default_repo
        base_path = parts[0].rstrip("//") if parts[0] else default_base_path
        name = parts[1]
    elif len(parts) == 3:
        repo = parts[0]
        base_path = parts[1]
        name = parts[2]
    else:
        fail('rule name has too many ":" chracters (more than 3): "{}"'.format(target))
    return rule_target_types.RuleTarget(repo = repo, base_path = base_path, name = name)

def _parse_external_dep(raw_target, lang_suffix = ""):
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
                        - (<repo>, <project>, <version>, <rule>)
                            This format should only really be used for accessing
                            third-party-tools rather than third-party
        lang_suffix: If provided, this will be appended for rules that do not
                     explicitly specify a rule (i.e. the first three types of
                     arguments mentioned above)

    Returns:
        Tuple of (ThirdPartyRuleTarget, version_string or None)
    """

    # We allow both tuples, and strings for legacy reasons
    if is_tuple(raw_target):
        target = raw_target
    elif is_unicode(raw_target) or is_string(raw_target):
        target = (raw_target,)
    else:
        fail("external dependency should be a tuple or string, " +
             "not {}".format(type(raw_target)))

    repo = rule_target_types.THIRD_PARTY_REPO
    if len(target) in (1, 2):
        project = target[0]
        rule = target[0] + lang_suffix
        version = target[1] if len(target) == 2 else None
    elif len(target) == 3:
        project = target[0]
        version = target[1]
        rule = target[2]
    elif len(target) == 4:
        repo = target[0]
        project = target[1]
        version = target[2]
        rule = target[3]
    else:
        fail(("illegal external dependency {}: must have 1, 2, or 3 elements").format(raw_target))

    return (rule_target_types.RuleTarget(repo, project, rule), version)

def _get_repo_and_repo_root(repo, platform):
    """
    Gets any additional paths that should be prepended to the package based on repo.

    This is primarily used to add third-party and third-party-tools paths
    """
    if repo == None:
        return (repo, "")
    elif repo == rule_target_types.THIRD_PARTY_REPO:
        return (None, third_party.get_build_path(platform))
    elif repo == rule_target_types.THIRD_PARTY_TOOLS_REPO:
        return (None, third_party.get_tools_path(platform))
    else:
        # If another cell is directly referenced, just keep its normal path
        return (repo, "")

def _to_label(repo, path, name):
    """
    Returns the target string to pass to buck

    Args:
        repo: The name of the cell, or None
        path: The path within the cell
        name: The name of the rule

    Returns:
        A fully qualified target string
    """

    return "{}//{}:{}".format(repo or "", path, name)

def _target_to_label(target, platform = None):
    """
    Converts a target struct  to a string to pass to buck

    Args:
        target: A struct returned from root_rule_target() or third_party_rule_target()
        platform: If provided, the fbcode platform to use

    Returns:
        A fully qualified target string
    """
    if target.base_path == None:
        fail("{} must not have a 'None' base_path".format(target))
    repo, repo_root = _get_repo_and_repo_root(target.repo, platform)
    return _to_label(repo, paths.join(repo_root, target.base_path), target.name)

target_utils = struct(
    RootRuleTarget = rule_target_types.RootRuleTarget,
    RuleTarget = rule_target_types.RuleTarget,
    ThirdPartyRuleTarget = rule_target_types.ThirdPartyRuleTarget,
    ThirdPartyToolRuleTarget = rule_target_types.ThirdPartyToolRuleTarget,
    is_rule_target = rule_target_types.is_rule_target,
    parse_external_dep = _parse_external_dep,
    parse_target = _parse_target,
    target_to_label = _target_to_label,
    to_label = _to_label,
)
