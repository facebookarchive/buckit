"""
Common methods to use in various thrift converters

"""

load("@bazel_skylib//lib:dicts.bzl", "dicts")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")

def _merge_sources_map(sources_map):
    """
    Takes a `sources_map` and flattens it into a mapping of names -> targets

    Args:
        sources_map: A map of {
            logical thrift file name: {
                    language-specific name (e.g. gen-cpp2/foo_data.h):
                    buck label that provides that source (e.g. //:rule=gen-cpp/foo_data.h)
                }
            }

    Returns:
        A merged mapping of language specific name -> buck label that provides that source
    """
    return dicts.add(*sources_map.values())

def _get_thrift_dep_target(base_path, rule_name):
    """
    Gets the translated target for a base_path and target. In fbcode, this
    will be a target_utils.RootRuleTarget. Outside of fbcode, we have to make sure that
    the specified third-party repo is used

    TODO: This can probably actually be removed. This was part of an OSS effort that'll
          end up being re-evaluated
    """
    target = target_utils.RootRuleTarget(base_path, rule_name)
    return target_utils.target_to_label(target)

# The capitalize method from the string will also make the
# other characters in the word lower case.  This version only
# makes the first character upper case.
def _capitalize_only(word):
    if len(word) > 0:
        return word[0].upper() + word[1:]
    return word

thrift_common = struct(
    capitalize_only = _capitalize_only,
    merge_sources_map = _merge_sources_map,
    get_thrift_dep_target = _get_thrift_dep_target,
)
