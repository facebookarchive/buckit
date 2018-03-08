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
import sys
import os
import platform


parser = argparse.ArgumentParser(
    description="Print out path:platform mapping for a list of subdirectories")
parser.add_argument('--platforms-file', required=True)
parser.add_argument('--repo', default='fbcode')
parser.add_argument('--architecture')
parser.add_argument('dirs', nargs='+')
args = parser.parse_args(sys.argv[1:])

# This file name is set by the command alias in tools/BUCK
sys.path.insert(0, os.path.dirname(os.path.abspath(args.platforms_file)))
from parsed_platforms import platforms
sys.path.pop(0)

dirs_for_cell = platforms.get(args.repo)
arch_string = args.architecture or platform.machine()

for user_dir in args.dirs:
    original_user_dir = user_dir
    while user_dir:
        if user_dir in dirs_for_cell and arch_string in dirs_for_cell[user_dir]:
            plat = dirs_for_cell[user_dir][arch_string]
            break
        user_dir = os.path.dirname(user_dir)
    else:
        plat = dirs_for_cell[''][arch_string]
    print('%s:%s' % (original_user_dir, plat))
