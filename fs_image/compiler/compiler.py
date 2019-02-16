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
import sys

from contextlib import ExitStack

from subvol_utils import Subvol

from .dep_graph import DependencyGraph
from .items import gen_parent_layer_items, LayerOpts
from .items_for_features import gen_items_for_features
from .subvolume_on_disk import SubvolumeOnDisk


# At the moment, the target names emitted by `image_feature` targets seem to
# be normalized the same way as those provided to us by `image_layer`.  If
# this were to ever change, this would be a good place to re-normalize them.
def make_target_path_map(targets_followed_by_paths):
    'Buck query_targets_and_outputs gives us `//target path/to/target/out`'
    if len(targets_followed_by_paths) % 2 != 0:
        raise RuntimeError(
            f'Odd-length --child-dependencies {targets_followed_by_paths}'
        )
    it = iter(targets_followed_by_paths)
    d = dict(zip(it, it))
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
        '--yum-from-repo-snapshot',
        help='Path to a binary taking `--install-root PATH -- SOME YUM ARGS`.',
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


def build_item(item, *, subvol, target_to_path, subvolumes_dir):
    '''
    Hack to avoid updating ALL items' build() to take unused args.
    Future: hide all these args inside a BuildContext struct instead,
    pass it to `Item.build`, and remove this function.
    '''
    if hasattr(item, 'build_resolves_targets'):
        assert not hasattr(item, 'build'), item
        item.build_resolves_targets(
            subvol=subvol,
            target_to_path=target_to_path,
            subvolumes_dir=subvolumes_dir,
        )
    else:
        item.build(subvol)


def build_image(args):
    subvol = Subvol(os.path.join(args.subvolumes_dir, args.subvolume_rel_path))
    target_to_path = make_target_path_map(args.child_dependencies)

    # This stack allows build items to hold temporary state on disk.
    with ExitStack() as exit_stack:
        dep_graph = DependencyGraph(itertools.chain(
            gen_parent_layer_items(
                args.child_layer_target,
                args.parent_layer_json,
                args.subvolumes_dir,
            ),
            gen_items_for_features(
                exit_stack=exit_stack,
                feature_paths=[args.child_feature_json],
                target_to_path=target_to_path,
            ),
        ))
        layer_opts = LayerOpts(
            layer_target=args.child_layer_target,
            yum_from_snapshot=args.yum_from_repo_snapshot,
        )
        # Creating all the builders up-front lets phases validate their input
        for builder in [
            builder_maker(items, layer_opts)
                for builder_maker, items in dep_graph.ordered_phases()
        ]:
            builder(subvol)
        # We cannot validate or sort `ImageItem`s until the phases are
        # materialized since the items may depend on the output of the phases.
        for item in dep_graph.gen_dependency_order_items(
            subvol.path().decode()
        ):
            build_item(
                item,
                subvol=subvol,
                target_to_path=target_to_path,
                subvolumes_dir=args.subvolumes_dir,
            )
        # Build artifacts should never change. Run this BEFORE the exit_stack
        # cleanup to enforce that the cleanup does not touch the image.
        subvol.set_readonly(True)

    try:
        return SubvolumeOnDisk.from_subvolume_path(
            # Converting to a path here does not seem too risky since this
            # class shouldn't have a reason to follow symlinks in the subvol.
            subvol.path().decode(),
            args.subvolumes_dir,
        )
    # The complexity of covering this is high, but the only thing that can
    # go wrong is a typo in the f-string.
    except Exception as ex:  # pragma: no cover
        raise RuntimeError(f'Serializing subvolume {subvol.path()}') from ex


if __name__ == '__main__':  # pragma: no cover
    build_image(parse_args(sys.argv[1:])).to_json_file(sys.stdout)
