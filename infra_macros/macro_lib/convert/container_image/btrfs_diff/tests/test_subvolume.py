#!/usr/bin/env python3
import copy
import unittest

from ..inode_id import InodeIDMap
from ..parse_dump import SendStreamItems
from ..subvolume import Subvolume

from .deepcopy_test import DeepCopyTestCase
from .subvolume_utils import (
    InodeRepr, serialize_subvol, serialized_subvol_add_fake_inode_ids,
)

# `unittest`'s output shortening makes tests much harder to debug.
unittest.util._MAX_LENGTH = 10e4


class SubvolumeTestCase(DeepCopyTestCase):
    def setUp(self):
        self.maxDiff = 10e4

    def _check_path(self, expected, subvol: Subvolume, path: str='.'):
        self.assertEqual(
            serialized_subvol_add_fake_inode_ids(expected),
            serialize_subvol(subvol, path.encode()),
        )

    def _check_subvolume(self):
        '''
        The `yield` statements in this generator allow `DeepCopyTestCase`
        to replace `ns.id_map` with a different object (either a `deepcopy`
        or a pre-`deepcopy` original from a prior run). See the docblock of
        `DeepCopyTestCase` for the details.

        This test does not try to exhaustively cover items like `chmod` and
        `write` that are applied by `IncompleteInode`, since that has its
        own unit test.  We exercise a few, to ensure that they get proxied.
        '''
        si = SendStreamItems

        # Make a tiny subvolume
        cat = Subvolume.new(id_map=InodeIDMap(description='cat'))
        cat = yield 'empty cat', cat
        self._check_path('(Dir)', cat)

        cat.apply_item(si.mkfile(path=b'dog'))
        self._check_path(('(Dir)', {'dog': '(File)'}), cat)

        cat.apply_item(si.chmod(path=b'dog', mode=0o755))
        cat = yield 'cat with chmodded dog', cat
        self._check_path(('(Dir)', {'dog': '(File m755)'}), cat)

        cat.apply_item(si.chmod(path=b'dog', mode=0o744))
        self._check_path(('(Dir)', {'dog': '(File m744)'}), cat)
        with self.assertRaisesRegex(RuntimeError, 'parent does not exist'):
            cat.apply_item(si.mkfifo(path=b'dir_to_del/fifo_to_del'))

        cat.apply_item(si.mkdir(path=b'dir_to_del'))
        cat.apply_item(si.mkfifo(path=b'dir_to_del/fifo_to_del'))
        cat_final_repr = ('(Dir)', {
            'dog': '(File m744)',
            'dir_to_del': ('(Dir)', {'fifo_to_del': '(FIFO)'}),
        })
        cat = yield 'final cat', cat
        self._check_path(cat_final_repr, cat)

        # Check some rename errors
        with self.assertRaisesRegex(RuntimeError, 'makes path its own subdir'):
            cat.apply_item(si.rename(path=b'dir_to_del', dest=b'dir_to_del/f'))

        with self.assertRaisesRegex(RuntimeError, 'source .* does not exist'):
            cat.apply_item(si.rename(path=b'not here', dest=b'dir_to_del/f'))

        with self.assertRaisesRegex(RuntimeError, 'cannot overwrite a dir'):
            cat.apply_item(si.rename(path=b'dog', dest=b'dir_to_del'))

        cat.apply_item(si.mkdir(path=b'temp_dir'))
        cat = yield 'cat with temp_dir', cat
        with self.assertRaisesRegex(RuntimeError, 'only overwrite an empty d'):
            cat.apply_item(si.rename(path=b'temp_dir', dest=b'dog'))
        with self.assertRaisesRegex(RuntimeError, 'since it has children'):
            cat.apply_item(si.rename(path=b'temp_dir', dest=b'dir_to_del'))

        # Cannot hardlink directories
        with self.assertRaisesRegex(RuntimeError, 'Cannot .* a directory'):
            cat.apply_item(si.link(path=b'temp_dir', dest=b'another_temp'))
        cat.apply_item(si.rmdir(path=b'temp_dir'))

        # Cannot act on nonexistent paths
        with self.assertRaisesRegex(RuntimeError, 'path does not exist'):
            cat.apply_item(si.chmod(path=b'temp_dir', mode=0o321))
        with self.assertRaisesRegex(RuntimeError, 'source does not exist'):
            cat.apply_item(si.link(path=b'temp_dir', dest=b'another_temp'))

        # Testing the above errors caused no changes
        cat = yield 'cat after error testing', cat
        self._check_path(cat_final_repr, cat)

        # Make a snapshot
        tiger = copy.deepcopy(cat)
        tiger.id_map.description = 'tiger'
        tiger = yield 'freshly copied tiger', tiger
        self._check_path(cat_final_repr, tiger)

        # rmdir/unlink errors, followed by successful removal
        with self.assertRaisesRegex(RuntimeError, 'since it has children'):
            tiger.apply_item(si.rmdir(path=b'dir_to_del'))
        with self.assertRaisesRegex(RuntimeError, 'Can only rmdir.* a dir'):
            tiger.apply_item(si.rmdir(path=b'dir_to_del/fifo_to_del'))
        tiger.apply_item(si.unlink(path=b'dir_to_del/fifo_to_del'))
        with self.assertRaisesRegex(RuntimeError, 'Cannot unlink.* a dir'):
            tiger.apply_item(si.unlink(path=b'dir_to_del'))
        tiger = yield 'tiger after rmdir/unlink errors', tiger
        tiger.apply_item(si.rmdir(path=b'dir_to_del'))
        tiger = yield 'tiger after rmdir', tiger
        self._check_path(('(Dir)', {'dog': '(File m744)'}), tiger)

        # Rename where the target does not exist
        tiger.apply_item(si.rename(path=b'dog', dest=b'wolf'))
        tiger = yield 'tiger after rename', tiger
        self._check_path(('(Dir)', {'wolf': '(File m744)'}), tiger)

        # Hardlinks, and modifyin the root directory
        tiger.apply_item(si.chown(path=b'.', uid=123, gid=456))
        tiger.apply_item(si.link(path=b'wolf', dest=b'tamaskan'))
        tiger.apply_item(si.chmod(path=b'tamaskan', mode=0o700))
        tiger = yield 'tiger after hardlink', tiger
        wolf = InodeRepr('(File m700)')
        tiger_penultimate_repr = ('(Dir o123:456)', {
            'wolf': wolf, 'tamaskan': wolf,
        })
        self._check_path(tiger_penultimate_repr, tiger)

        # Renaming the same inode is a no-op
        tiger.apply_item(si.rename(path=b'tamaskan', dest=b'wolf'))
        tiger = yield 'tiger after same-inode rename', tiger
        self._check_path(tiger_penultimate_repr, tiger)

        # Hardlinks do not overwrite targets
        tiger.apply_item(si.mknod(path=b'somedev', mode=0o20444, dev=0x4321))
        with self.assertRaisesRegex(RuntimeError, 'Destination .* exists'):
            tiger.apply_item(si.link(path=b'somedev', dest=b'wolf'))
        tiger = yield 'tiger after mkdev etc', tiger

        # A rename that overwrites an existing file.
        tiger.apply_item(si.rename(path=b'somedev', dest=b'wolf'))
        tiger = yield 'tiger after overwriting rename', tiger
        self._check_path(('(Dir o123:456)', {
            'wolf': '(Char m444 4321)', 'tamaskan': '(File m700)',
        }), tiger)

        # Mutating the snapshot leaves the parent subvol intact
        cat = yield 'cat after tiger mutations', cat
        self._check_path(cat_final_repr, cat)

    def test_subvolume(self):
        self.check_deepcopy_at_each_step(self._check_subvolume)


if __name__ == '__main__':
    unittest.main()
