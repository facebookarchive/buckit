#!/usr/bin/env python3
'''
Runs `yum` against a snapshot of the `container_image/rpm` test repos that
are built by `tests/build_repos.py`. Used in the image compiler unit tests.
'''
import json
import os

from ..common import init_logging, Path
from ..yum_from_snapshot import add_common_yum_args, yum_from_snapshot


def yum_from_test_snapshot(install_root: 'AnyStr', yum_args: 'List[AnyStr]'):
    # This works in @mode/opt since the snapshot is baked into the XAR
    snapshot_dir = Path(os.path.dirname(__file__)) / 'snapshot'
    yum_from_snapshot(
        storage_cfg=json.dumps({
            'key': 'test',
            'kind': 'filesystem',
            'base_dir': (snapshot_dir / 'storage').decode(),
        }),
        snapshot_dir=snapshot_dir / 'repos',
        install_root=Path(install_root),
        yum_args=yum_args,
    )


# CLI tested indirectly via the image compiler's test image targets.
if __name__ == '__main__':  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_yum_args(parser)
    args = parser.parse_args()

    init_logging()

    yum_from_test_snapshot(args.install_root, args.yum_args)
