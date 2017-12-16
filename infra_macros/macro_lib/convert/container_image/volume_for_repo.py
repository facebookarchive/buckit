#!/usr/bin/env python2
#
# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

with allow_unsafe_import():  # noqa: F821
    # Future: Is our usage of os.path.abspath actually unsafe? What is the
    # saner way to get siblings of `__file__`?
    import os
    import subprocess


def get_volume_for_current_repo(min_available_bytes):
    '''
    Multiple repos need to be able to concurrently build images on the same
    host.  The cleanest way to achieve such isolation is to supply each repo
    with its own volume, which will store the repo's image build outputs.

    It is easiest to back this volume with a loop device. The appropriate
    size of the loop device depends on the expected size of the target being
    built.  To address this this by ensuring that prior to every build, the
    volume has at least a specified amount of space.  The default is large
    enough for most builds, but really huge `image_layer` targets can
    further increase their requested `min_available_bytes`.

    Image-build tooling **must never** access paths in this volume without
    going through this function.  Otherwise, the volume will not get
    remounted correctly if the host containing the repo got rebooted.
    '''
    cur_file_dir = os.path.dirname(os.path.abspath(__file__))
    artifacts_dir = os.path.join(cur_file_dir, '_build_artifacts')
    volume_dir = os.path.join(artifacts_dir, 'volume')
    subprocess.check_call([
        # While Buck probably does not call this concurrently under normal
        # circumstances, the worst-case outcome is that we lose or corrupt
        # the whole buld cache, so add some locking to be on the safe side.
        'flock',
        os.path.join(artifacts_dir, '.lock.set_up_volume.sh.never.rm.or.mv'),
        'sudo',
        os.path.join(cur_file_dir, 'set_up_volume.sh'),
        str(min_available_bytes),
        os.path.join(artifacts_dir, 'image.btrfs'),
        volume_dir,
    ])
    return volume_dir
