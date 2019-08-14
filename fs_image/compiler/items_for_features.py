#!/usr/bin/env python3
'Makes Items from the JSON that was produced by the Buck target image_feature'
import json

from typing import Iterable, Mapping, Union

from .items import (
    InstallFileItem, MakeDirsItem, MountItem, RemovePathItem, RpmActionItem,
    SymlinkToDirItem, SymlinkToFileItem, tarball_item_factory,
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
    elif type(x) in [int, float, str, bool, type(None)]:
        return x
    assert False, f'Unknown {type(x)} for {x}'  # pragma: no cover


def gen_items_for_features(
    *, exit_stack, features_or_paths: Iterable[Union[str, dict]],
    target_to_path: Mapping[str, str],
):
    key_to_item_factory = {
        'install_files': InstallFileItem,
        'make_dirs': MakeDirsItem,
        'mounts': MountItem,
        'rpms': RpmActionItem,
        'remove_paths': RemovePathItem,
        'symlinks_to_dirs': SymlinkToDirItem,
        'symlinks_to_files': SymlinkToFileItem,
        'tarballs': lambda **kwargs: tarball_item_factory(exit_stack, **kwargs),
    }

    for feature_or_path in features_or_paths:
        if isinstance(feature_or_path, str):
            with open(feature_or_path) as f:
                items = replace_targets_by_paths(json.load(f), target_to_path)
        else:
            items = feature_or_path

        yield from gen_items_for_features(
            exit_stack=exit_stack,
            features_or_paths=items.pop('features', []),
            target_to_path=target_to_path,
        )

        target = items.pop('target')
        for key, item_factory in key_to_item_factory.items():
            for dct in items.pop(key, []):
                try:
                    yield item_factory(from_target=target, **dct)
                except Exception as ex:  # pragma: no cover
                    raise RuntimeError(
                        f'Failed to process {key}: {dct} from target '
                        f'{target}, please read the exception above.'
                    ) from ex

        assert not items, f'Unsupported items: {items}'
