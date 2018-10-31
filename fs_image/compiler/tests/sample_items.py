#!/usr/bin/env python3
import os

from ..items import (
    CopyFileItem, FilesystemRootItem, MakeDirsItem, MultiRpmAction,
    RpmActionType, TarballItem,
)


T_BASE = '//fs_image/compiler/tests'
# Use the "debug", human-readable forms of the image_feature targets here,
# since that's what we are testing.
T_DIRS = f'{T_BASE}:feature_dirs'
T_BAD_DIR = f'{T_BASE}:feature_bad_dir'
T_TAR = f'{T_BASE}:feature_tar_and_rpms'
T_COPY_DIRS_TAR = f'{T_BASE}:feature_copy_dirs_tar_and_rpms'
T_HELLO_WORLD_TAR = f'{T_BASE}:hello_world.tar'

TARGET_ENV_VAR_PREFIX = 'test_image_feature_path_to_'
TARGET_TO_PATH = {
    '{}:{}'.format(T_BASE, target[len(TARGET_ENV_VAR_PREFIX):]): path
        for target, path in os.environ.items()
            if target.startswith(TARGET_ENV_VAR_PREFIX)
}
# We rely on Buck setting the environment via the `env =` directive.
assert T_HELLO_WORLD_TAR in TARGET_TO_PATH, 'You must use `buck test`'


def mangle(feature_target):
    return feature_target + (
        '_IF_YOU_REFER_TO_THIS_RULE_YOUR_DEPENDENCIES_WILL_BE_BROKEN_'
        'SO_DO_NOT_DO_THIS_EVER_PLEASE_KTHXBAI'
    )


# This should be a faithful transcription of the `image_feature`
# specifications in `test/TARGETS`.  The IDs currently have no semantics,
# existing only to give names to specific items.
ID_TO_ITEM = {
    '/': FilesystemRootItem(from_target=None),
    'foo/bar': MakeDirsItem(
        from_target=T_DIRS, into_dir='/', path_to_make='/foo/bar'
    ),
    'foo/bar/baz': MakeDirsItem(
        from_target=T_DIRS, into_dir='/foo/bar', path_to_make='baz'
    ),
    'foo/borf/beep': MakeDirsItem(
        from_target=T_BAD_DIR,
        into_dir='/foo',
        path_to_make='borf/beep',
        user='uuu',
        group='ggg',
        mode='mmm',
    ),
    'foo/bar/hello_world.tar': CopyFileItem(
        from_target=T_COPY_DIRS_TAR,
        source=TARGET_TO_PATH[T_HELLO_WORLD_TAR],
        dest='/foo/bar/',
    ),
    'foo/bar/hello_world_again.tar': CopyFileItem(
        from_target=T_COPY_DIRS_TAR,
        source=TARGET_TO_PATH[T_HELLO_WORLD_TAR],
        dest='/foo/bar/hello_world_again.tar',
        group='nobody',
    ),
    'foo/borf/hello_world': TarballItem(
        from_target=T_TAR,
        tarball=TARGET_TO_PATH[T_HELLO_WORLD_TAR],
        into_dir='foo/borf',
    ),
    'foo/hello_world': TarballItem(
        from_target=T_TAR,
        tarball=TARGET_TO_PATH[T_HELLO_WORLD_TAR],
        into_dir='foo',
    ),
    '.rpms/install/rpm-test-mice': MultiRpmAction.new(
        rpms=frozenset({'rpm-test-mice'}),
        action=RpmActionType.install,
        yum_from_snapshot='/fake/yum',
    ),
    '.rpms/remove_if_exists/rpm-test-{carrot,milk}': MultiRpmAction.new(
        rpms=frozenset({'rpm-test-milk', 'rpm-test-carrot'}),
        action=RpmActionType.remove_if_exists,
        yum_from_snapshot='/fake/yum',
    ),
}
