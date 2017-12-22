#!/usr/bin/env python3
'Makes Items from the JSON that was produced by the Buck target image_feature'
import json

from items import MakeDirsItem, TarballItem, CopyFileItem


# XXX for JSON only etc
def replace_targets_by_paths(x, target_to_filename):
    if type(x) is dict:
        if '__BUCK_TARGET' in x:
            assert len(x) == 1, x
            (_, target), = x.items()
            filename = target_to_filename.get(target)
            assert filename, f'{target} not in {target_to_filename}'
            return filename
        return {
            k: replace_targets_by_paths(v, target_to_filename)
                for k, v in x.items()
        }
    elif type(x) is list:
        return [replace_targets_by_paths(v, target_to_filename) for v in x]
    elif type(x) in [int, float, str]:
        return x
    assert False, 'Unknown {type(x)} for {x}'  # pragma: no cover


def gen_items_for_features(feature_filenames, target_to_filename):
    key_to_item_class = {
        'make_dirs': MakeDirsItem,
        'tarballs': TarballItem,
        'copy_files': CopyFileItem,
    }
    for feature_filename in feature_filenames:
        with open(feature_filename) as f:
            items = replace_targets_by_paths(json.load(f), target_to_filename)

            yield from gen_items_for_features(
                items.pop('features', []), target_to_filename,
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

            for _rpm_name, _action in items.pop('rpms', {}).items():
                raise NotImplementedError(  # pragma: no cover
                    'No RPM support yet'
                )

            assert not items, f'Unsupported items: {items}'
