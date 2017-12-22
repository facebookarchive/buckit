#!/usr/bin/env python2
#
# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

# Mock to let unit tests work properly
if 'allow_unsafe_import':
    from contextlib import contextmanager

    @contextmanager
    def allow_unsafe_import():
        yield


with allow_unsafe_import():  # noqa: F821
    import os
    import subprocess


# Exposed for tests
IMAGE_FILE = 'image.btrfs'
VOLUME_DIR = 'volume'


def get_per_repo_artifacts_dir():  # pragma: no cover
    '''
    This is intended to work:
     - under Buck's internal macro interpreter, and
     - using the system python from `facebookexperimental/buckit`.

    We cannot unit-test this because our unit-tests run via LPARS, which
    break the assumption that the Python source path is located in the repo.
    '''
    path_suffix = \
        '/infra_macros/macro_lib/convert/container_image/volume_for_repo.py'
    # This ought to work both internally under Buck and for BuckIt.
    if not __file__.endswith(path_suffix):
        raise RuntimeError('__file__ {} expected to end in {}'.format(
            __file__, path_suffix
        ))
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '_build_artifacts',
    )


def get_volume_for_current_repo(min_free_bytes, artifacts_dir):
    '''
    Multiple repos need to be able to concurrently build images on the same
    host.  The cleanest way to achieve such isolation is to supply each repo
    with its own volume, which will store the repo's image build outputs.

    It is easiest to back this volume with a loop device. The appropriate
    size of the loop device depends on the expected size of the target being
    built.  To address this this by ensuring that prior to every build, the
    volume has at least a specified amount of space.  The default is large
    enough for most builds, but really huge `image_layer` targets can
    further increase their requested `min_free_bytes`.

    Image-build tooling **must never** access paths in this volume without
    going through this function.  Otherwise, the volume will not get
    remounted correctly if the host containing the repo got rebooted.
    '''
    try:
        os.mkdir(artifacts_dir)
    except OSError:
        pass  # artifacts_dir might already exist

    volume_dir = os.path.join(artifacts_dir, VOLUME_DIR)
    subprocess.check_call([
        # While Buck probably does not call this concurrently under normal
        # circumstances, the worst-case outcome is that we lose or corrupt
        # the whole buld cache, so add some locking to be on the safe side.
        'flock',
        os.path.join(artifacts_dir, '.lock.set_up_volume.sh.never.rm.or.mv'),
        'sudo',
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'set_up_volume.sh',
        ),
        str(int(min_free_bytes)),  # Accepts floats & ints
        os.path.join(artifacts_dir, IMAGE_FILE),
        volume_dir,
    ])
    return volume_dir
