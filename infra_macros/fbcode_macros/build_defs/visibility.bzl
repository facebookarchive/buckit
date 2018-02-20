# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
Functions that handle correcting 'visiblity' arguments
"""

def get_visibility(visibility_attr):
    """
    Returns either the provided visibility list, or a default visibility if None
    """
    if visibility_attr == None:
        return ["PUBLIC"]
    else:
        return visibility_attr
