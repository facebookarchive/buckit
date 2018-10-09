load("@fbcode_macros//build_defs:rule_target_types.bzl", "rule_target_types")

# Re-export from rule_target_types so that the common case usage is to use target_utils,
# but having a separate 'types' file allows us to break a few cyclic dependencies down
# the road (e.g. on "third-party" when we're doing some of the path resolution in
# to_label() and the like

target_utils = struct(
    RootRuleTarget = rule_target_types.RootRuleTarget,
    RuleTarget = rule_target_types.RuleTarget,
    ThirdPartyRuleTarget = rule_target_types.ThirdPartyRuleTarget,
    ThirdPartyToolRuleTarget = rule_target_types.ThirdPartyToolRuleTarget,
    is_rule_target = rule_target_types.is_rule_target,
)
