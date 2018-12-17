"""
Common methods to use in various thrift converters

"""

load("@bazel_skylib//lib:dicts.bzl", "dicts")

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

thrift_common = struct(
    merge_sources_map = _merge_sources_map,
)
