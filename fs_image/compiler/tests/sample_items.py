#!/usr/bin/env python3
import os

from ..items import (
    CopyFileItem, FilesystemRootItem, MakeDirsItem, RpmActionItem,
    RpmAction, SymlinkToDirItem, SymlinkToFileItem, TarballItem,
)


T_BASE = '//fs_image/compiler/tests'
# Use the "debug", human-readable forms of the image_feature targets here,
# since that's what we are testing.
T_DIRS = f'{T_BASE}:feature_dirs'
T_BAD_DIR = f'{T_BASE}:feature_bad_dir'
T_SYMLINKS = f'{T_BASE}:feature_symlinks'
T_TAR = f'{T_BASE}:feature_tar_and_rpms'
T_KITCHEN_SINK = f'{T_BASE}:feature_kitchen_sink'
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
    'foo/fighter': SymlinkToDirItem(
        from_target=T_SYMLINKS,
        dest='/foo/fighter',
        source='/foo/bar',
    ),
    'foo/face': SymlinkToDirItem(
        from_target=T_SYMLINKS,
        dest='/foo/face',
        source='/foo/bar',
    ),
    'foo/bar/baz/bar': SymlinkToDirItem(  # Rsync style
        from_target=T_SYMLINKS,
        dest='/foo/bar/baz/',
        source='/foo/bar',
    ),
    'foo/hello_world.tar': CopyFileItem(
        from_target=T_SYMLINKS,
        source=TARGET_TO_PATH[T_HELLO_WORLD_TAR],
        dest='/foo/hello_world.tar',
    ),
    'foo/symlink_to_hello_world.tar': SymlinkToFileItem(
        from_target=T_SYMLINKS,
        dest='/foo/symlink_to_hello_world.tar',
        source='/foo/hello_world.tar',
    ),
    'foo/bar/hello_world.tar': CopyFileItem(
        from_target=T_KITCHEN_SINK,
        source=TARGET_TO_PATH[T_HELLO_WORLD_TAR],
        dest='/foo/bar/',
    ),
    'foo/bar/hello_world_again.tar': CopyFileItem(
        from_target=T_KITCHEN_SINK,
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
    '.rpms/install/rpm-test-mice': RpmActionItem(
        from_target=T_TAR,
        name='rpm-test-mice',
        action=RpmAction.install,
    ),
    '.rpms/remove_if_exists/rpm-test-carrot': RpmActionItem(
        from_target=T_TAR,
        name='rpm-test-carrot',
        action=RpmAction.remove_if_exists,
    ),
    '.rpms/remove_if_exists/rpm-test-milk': RpmActionItem(
        from_target=T_TAR,
        name='rpm-test-milk',
        action=RpmAction.remove_if_exists,
    ),
}


# Imitates the output of `DependencyGraph.ordered_phases` for `test-compiler`
ORDERED_PHASES = (
    (FilesystemRootItem.get_phase_builder, ['/']),
    (RpmActionItem.get_phase_builder, ['.rpms/install/rpm-test-mice']),
    (RpmActionItem.get_phase_builder, [
        '.rpms/remove_if_exists/rpm-test-carrot',
        '.rpms/remove_if_exists/rpm-test-milk',
    ]),
)
