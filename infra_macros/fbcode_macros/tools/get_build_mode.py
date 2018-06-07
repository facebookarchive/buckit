# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import argparse
import json
import sys
import os


parser = argparse.ArgumentParser(
    description="Print out path:build_mode mapping for a list of subdirectories")
parser.add_argument("--build-modes-file", required=True)
parser.add_argument("--repo", default="fbcode")
parser.add_argument("dirs", nargs="+")
args = parser.parse_args(sys.argv[1:])

# This file name is set by the command alias in tools/BUCK
sys.path.insert(0, os.path.dirname(os.path.abspath(args.build_modes_file)))
from parsed_build_modes import build_modes
sys.path.pop(0)

dirs_for_cell = build_modes.get(args.repo)

for user_dir in args.dirs:
    original_user_dir = user_dir
    while user_dir:
        if user_dir in dirs_for_cell:
            build_mode = {
                k: v._asdict()
                for k, v in dirs_for_cell[user_dir].items()
            }
            break
        user_dir = os.path.dirname(user_dir)
    else:
        build_mode = {}
    print("%s:%s" % (original_user_dir, json.dumps(build_mode, sort_keys=True)))
