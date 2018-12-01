_RuleTargetProvider = provider(fields = [
    "name",  # The name of the rule
    "base_path",  # The base package within the repository
    "repo",  # Either the cell, None (for the root cell), or one of the special 'third party' cells
])

# The name of the 'third-party' repo
_THIRD_PARTY_REPO = "third-party"

# The name of the 'third-party-tools' repo
_THIRD_PARTY_TOOLS_REPO = "third-party-tools"

_THIRD_PARTY_REPOS = (_THIRD_PARTY_REPO, _THIRD_PARTY_TOOLS_REPO)

def _RuleTarget(repo, base_path, name):
    """
    Returns a struct representing some sort of RuleTarget (Similar to a `Label` object in bazel)

    Args:
        repo: The repository. This can be `None` for the "root" repository, one of
              `third-party` or `third-party-tools` if this represents a third party
              target that may need special handling, or any other arbitrary cell name
        base_path: The base path / package within the repository
        name: The name of the rule

    Returns:
        A RuleTarget object with repo, base_path, name
    """
    return _RuleTargetProvider(name = name, base_path = base_path, repo = repo)

def _RootRuleTarget(base_path, name):
    """ Returns a RuleTarget for the root repository. repo is set to None in this case """
    return _RuleTargetProvider(
        name = name,
        base_path = base_path,
        repo = None,
    )

def _ThirdPartyRuleTarget(project, rule_name):
    """
    Returns a RuleTarget for a third-party project.

    Args:
        project: The name of the third-party project, used in base_path
        rule_name: The name of the rule in the build file

    Returns:
        A RuleTarget object with the repo set to `third-party`
    """
    return _RuleTargetProvider(
        name = rule_name,
        base_path = project,
        repo = _THIRD_PARTY_REPO,
    )

def _ThirdPartyToolRuleTarget(project, rule_name):
    """
    Returns a RuleTarget for a third-party tool project.

    Args:
        project: The name of the third-party project, used in base_path
        rule_name: The name of the rule in the build file

    Returns:
        A RuleTarget object with the repo set to `third-party-tools`
    """
    return _RuleTargetProvider(
        name = rule_name,
        base_path = project,
        repo = _THIRD_PARTY_TOOLS_REPO,
    )

def _is_rule_target(target):
    """ Determines whether or not `target` was created by one of the *RuleTarget methods """

    # TODO: Once the rest of the python namedtuples are removed, and skylark supports
    #       type(target) == type(_RuleTarget), make this do a type() comparison
    return hasattr(target, "repo")

rule_target_types = struct(
    RootRuleTarget = _RootRuleTarget,
    RuleTarget = _RuleTarget,
    THIRD_PARTY_REPO = _THIRD_PARTY_REPO,
    THIRD_PARTY_REPOS = _THIRD_PARTY_REPOS,
    THIRD_PARTY_TOOLS_REPO = _THIRD_PARTY_TOOLS_REPO,
    ThirdPartyRuleTarget = _ThirdPartyRuleTarget,
    ThirdPartyToolRuleTarget = _ThirdPartyToolRuleTarget,
    is_rule_target = _is_rule_target,
)
