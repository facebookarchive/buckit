#!/usr/bin/env python3
'''
This is normally invoked by the `image_layer` Buck macro converter.

This compiler builds a btrfs subvolume in
  <--subvolumes-dir>/<--subvolume-rel-path>

To do so, it parses `--child-feature-json` and the `--child-dependencies`
that referred therein, creates `ImageItems`, sorts them in dependency order,
and invokes `.build()` to apply each item to actually construct the subvol.
'''

import argparse
import itertools
import os
import subprocess
import sys

from subvol_utils import Subvol

from .dep_graph import dependency_order_items
from .items import gen_parent_layer_items
from .items_for_features import gen_items_for_features
from .subvolume_on_disk import SubvolumeOnDisk


# At the moment, the target names emitted by `image_feature` targets seem to
# be normalized the same way as those provided to us by `image_layer`.  If
# this were to ever change, this would be a good place to re-normalize them.
def make_target_filename_map(targets_followed_by_filenames):
    'Buck query_targets_and_outputs gives us `//target path/to/target/out`'
    if len(targets_followed_by_filenames) % 2 != 0:
        raise RuntimeError(
            f'Odd-length --child-dependencies {targets_followed_by_filenames}'
        )
    it = iter(targets_followed_by_filenames)
    d = dict(zip(it, it))
    # A hacky check to ensures that the target corresponds to the path.  We
    # can remove this if we absolutely trust the Buck output.
    if not all(
        t.replace('//', '/').replace(':', '/') in f for t, f in d.items()
    ):
        raise RuntimeError(f'Not every target matches its output: {d}')
    return d


def parse_args(args):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        '--subvolumes-dir', required=True,
        help='A directory on a btrfs volume to store the compiled subvolume '
            'representing the new layer',
    )
    # We separate this from `--subvolumes-dir` in order to help keep our
    # JSON output ignorant of the absolute path of the repo.
    parser.add_argument(
        '--subvolume-rel-path', required=True,
        help='Path underneath --subvolumes-dir where we should create '
            'the subvolume. Note that all path components but the basename '
            'should already exist.',
    )
    parser.add_argument(
        '--parent-layer-json',
        help='Path to the JSON output of the parent `image_layer` target',
    )
    parser.add_argument(
        '--child-layer-target', required=True,
        help='The name of the Buck target describing the layer being built',
    )
    parser.add_argument(
        '--child-feature-json', required=True,
        help='The path of the JSON output of the `image_feature` that was '
            'auto-generated for the layer being built',
    )
    parser.add_argument(
        '--child-dependencies',
        nargs=argparse.REMAINDER, metavar=['TARGET', 'PATH'], default=(),
        help='Consumes the remaining arguments on the command-line, with '
            'arguments at positions 1, 3, 5, 7, ... used as Buck target names '
            '(to be matched with the targets in per-feature JSON outputs). '
            'The argument immediately following each target name must be a '
            'path to the output of that target on disk.',
    )
    return parser.parse_args(args)


def build_image(args):
    subvol = Subvol(os.path.join(args.subvolumes_dir, args.subvolume_rel_path))

    for item in dependency_order_items(
        itertools.chain(
            gen_parent_layer_items(
                args.child_layer_target,
                args.parent_layer_json,
                args.subvolumes_dir,
            ),
            gen_items_for_features(
                [args.child_feature_json],
                make_target_filename_map(args.child_dependencies),
            ),
        )
    ):
        item.build(subvol)

    try:
        return SubvolumeOnDisk.from_subvolume_path(
            subvol.path().decode(),
            args.subvolumes_dir,
            args.subvolume_rel_path,
        )
    except Exception as ex:
        raise RuntimeError(f'Serializing subvolume {subvol.path()}') from ex


if __name__ == '__main__':  # pragma: no cover
    build_image(parse_args(sys.argv[1:])).to_json_file(sys.stdout)
