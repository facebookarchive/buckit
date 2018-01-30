# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

"""
User configurable settings for the buck macro library
"""

def _read_string(section, field, default):
    """
    Read a string value from .buckconfig
    """
    return read_config(section, field, default)

def _get_third_party_buck_directory():
    """
    An additional directory that should be inserted into all third party paths in a monorepo
    """
    return _read_string('fbcode', 'third_party_buck_directory', '')

config = struct(
    get_third_party_buck_directory=_get_third_party_buck_directory,
)
