#!/usr/bin/env python3
'Makes Items from the JSON that was produced by the Buck target image_feature'
import json

from typing import Iterable, Mapping, Optional

from .items import (
    CopyFileItem, MakeDirsItem, MultiRpmAction, TarballItem, RpmActionType,
)


def replace_targets_by_paths(x, target_to_path: Mapping[str, str]):
    '''
    JSON-serialized image features store single-item dicts of the form
    {'__BUCK_TARGET': '//target:path'} whenever the compiler requires a path
    to another target.  This is because actual paths would break Buck
    caching, and would not survive repo moves.  Then, at runtime, the
    compiler receives a dictionary of target-to-path mappings as
    `--child-dependencies`, and performs the substitution in any image
    feature JSON it consumes.
    '''
    if type(x) is dict:
        if '__BUCK_TARGET' in x:
            assert len(x) == 1, x
            (_, target), = x.items()
            path = target_to_path.get(target)
            if not path:
                raise RuntimeError(f'{target} not in {target_to_path}')
            return path
        return {
            k: replace_targets_by_paths(v, target_to_path)
                for k, v in x.items()
        }
    elif type(x) is list:
        return [replace_targets_by_paths(v, target_to_path) for v in x]
    elif type(x) in [int, float, str]:
        return x
    assert False, 'Unknown {type(x)} for {x}'  # pragma: no cover


def gen_items_for_features(
    feature_paths: Iterable[str],
    target_to_path: Mapping[str, str],
    yum_from_repo_snapshot: Optional[str],
):
    key_to_item_class = {
        'make_dirs': MakeDirsItem,
        'tarballs': TarballItem,
        'copy_files': CopyFileItem,
    }
    action_to_rpms = {action: set() for action in RpmActionType}
    for feature_path in feature_paths:
        with open(feature_path) as f:
            items = replace_targets_by_paths(json.load(f), target_to_path)

            yield from gen_items_for_features(
                feature_paths=items.pop('features', []),
                target_to_path=target_to_path,
                yum_from_repo_snapshot=yum_from_repo_snapshot,
            )

            target = items.pop('target')
            for key, item_class in key_to_item_class.items():
                for dct in items.pop(key, []):
                    try:
                        yield item_class(from_target=target, **dct)
                    except Exception as ex:  # pragma: no cover
                        raise RuntimeError(
                            f'Failed to process {key}: {dct} from target '
                            f'{target}, please read the exception above.'
                        ) from ex

            # Note that at present, we don't attempt to attribute RPMs to
            # the build target(s) that requested them.
            for dct in items.pop('rpms', []):
                action_to_rpms[RpmActionType(dct['action'])].add(dct['name'])

            assert not items, f'Unsupported items: {items}'
    for action, rpms in action_to_rpms.items():
        if rpms:
            yield MultiRpmAction.new(
                action=action,
                rpms=frozenset(rpms),
                yum_from_snapshot=yum_from_repo_snapshot,
            )
