#!/usr/bin/env python3
'''
This is normally invoked by the `image_layer` Buck macro converter.

This compiler builds a btrfs subvolume in
  <--subvolumes-dir>/<--subvolume-name>:<subvolume-version>

To do so, it parses `--child-feature-json` and the `--child-dependencies`
that referred therein, creates `ImageItems`, sorts them in dependency order,
and emits image builder subcommands for the sorted items.
'''

import argparse
import itertools
import subprocess
import sys

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
        '--image-build-command', required=True,
        help='Path to the image builder binary',
    )
    parser.add_argument(
        '--subvolumes-dir', required=True,
        help='A directory on a btrfs volume to store the compiled subvolume '
            'representing the new layer',
    )
    parser.add_argument(
        '--subvolume-name', required=True,
        help='The first part of the subvolume directory name',
    )
    parser.add_argument(
        '--subvolume-version', required=True,
        help='The second part of the subvolume directory name',
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
    cmd = [
        # The various btrfs ioctls we will perform most likely all require
        # root.  Future: look into using more granular capabilities here.
        'sudo',
        args.image_build_command,
        'image', 'build',
        '--no-pkg', '--no-export', '--no-clean-built-layer',
        '--print-buck-plumbing',
        '--tmp-volume', args.subvolumes_dir,
        '--name', args.subvolume_name,
        '--version', args.subvolume_version,
        *itertools.chain.from_iterable(
            item.build_subcommand() for item in dependency_order_items(
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
            )
        ),
    ]

    try:
        # This throws away the return code, but it's not very useful anyhow.
        output = subprocess.check_output(cmd)
    except Exception as ex:  # pragma: no cover
        raise RuntimeError(f'While running {cmd}') from ex

    try:
        return SubvolumeOnDisk.from_build_buck_plumbing(
            output,
            args.subvolumes_dir,
            args.subvolume_name,
            args.subvolume_version,
        )
    except Exception as ex:  # pragma: no cover
        raise RuntimeError(f'While parsing output {output} of {cmd}') from ex


def main():  # pragma: no cover
    'Invoked by ../compiler.py'
    build_image(parse_args(sys.argv[1:])).to_json_file(sys.stdout)
