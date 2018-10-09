load("@fbcode_macros//build_defs:rule_target_types.bzl", "rule_target_types")

# Re-export from rule_target_types so that the common case usage is to use target_utils,
# but having a separate 'types' file allows us to break a few cyclic dependencies down
# the road (e.g. on "third-party" when we're doing some of the path resolution in
# to_label() and the like

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

target_utils = struct(
    RootRuleTarget = rule_target_types.RootRuleTarget,
    RuleTarget = rule_target_types.RuleTarget,
    ThirdPartyRuleTarget = rule_target_types.ThirdPartyRuleTarget,
    ThirdPartyToolRuleTarget = rule_target_types.ThirdPartyToolRuleTarget,
    is_rule_target = rule_target_types.is_rule_target,
    parse_target = _parse_target,
)
