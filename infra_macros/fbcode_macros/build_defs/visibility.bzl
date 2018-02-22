# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Functions that handle correcting 'visiblity' arguments
"""

# DO NOT MODIFY THIS LIST.  This grandfathers in some places where non-
# experimental rules depend on experimental rules and should not grow.  Please
# reach out to fbcode foundation with any questions.
# Also: Depsets are kind of dumb, and don't let you do fast membership lookups.
# simulating with dict per https://docs.bazel.build/versions/master/skylark/lib/depset.html
EXPERIMENTAL_WHITELIST = {
    ('experimental/deeplearning', 'all_lua'): None,
    ('experimental/deeplearning/mobile-vision/segmentation/tools/create_coco_format_dataset/tests', 'analyze_json_lib'): None,
    ('experimental/deeplearning/ntt/detection_caffe2/lib', 'lib'): None,
    ('experimental/deeplearning/vajdap/xray', 'xray_lib'): None,
    ('experimental/deeplearning/vision/cluster_utils', 'io'): None,
    ('experimental/deeplearning/wym/classification_attribute/datasets', 'attr_data'): None,
    ('experimental/deeplearning/zyan3/sherlock/visual_sherlock/meter', 'classerrormeter'): None,
    ('experimental/deeplearning/zyan3/sherlock/visual_sherlock/meter', 'mapmeter'): None,
    ('experimental/everstore/orphaned_needles/WorkitemList', 'workitemlist_client_lib'): None,
    ('experimental/everstore/orphaned_needles/WorkitemList/if', 'workitemserver_thrift-py'): None,
    ('experimental/guruqu/transformers', 'segmax_predict'): None,
    ('experimental/pshinghal/dummy_service', 'thrift-py'): None,
}

def get_visibility_for_base_path(visibility_attr, name_attr, base_path):
    """
    Gets the default visibility for a given base_path.

    If the base_path is an experimental path and isn't in a whitelist, this
    ensures that the target is only visible to the experimental directory.
    Otherwise, this returns either a default visibility if visibility_attr's
    value is None, or returns the original value.

    Args:
        visibility_attr: The value of the rule's 'visibility' attribute, or None
        name_attr: The name of the rule
        base_path: The base path to the package that the target resides in.
                   This will eventually be removed, and native.package() will
                   be used instead.

    Returns:
        A visibility array
    """
    if (base_path.startswith("experimental/") and 
            (base_path, name_attr) not in EXPERIMENTAL_WHITELIST):
        return ["//experimental/..."]

    if visibility_attr == None:
        return ["PUBLIC"]
    else:
        return visibility_attr


def get_visibility(visibility_attr):
    """
    Returns either the provided visibility list, or a default visibility if None
    """
    if visibility_attr == None:
        return ["PUBLIC"]
    else:
        return visibility_attr
