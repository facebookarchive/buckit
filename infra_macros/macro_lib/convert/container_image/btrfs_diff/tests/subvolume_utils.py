#!/usr/bin/env python3
'''
These utilities let us to concisely representation subtrees of a `Subvolume`
in tests.  Refer to `test_subvolume.py` for usage examples.  Use `InodeRepr`
for hardlinks.
'''
import os

from itertools import count
from typing import NamedTuple


class InodeRepr(NamedTuple):
    '''
    Use this instead of a plain string to represent an inode that occurs
    more than once in the filesystem (i.e. hardlinks).
    '''
    ino_repr: str


class FakeInodeIds:
    def __init__(self):
        self.counter = count()
        self.nonce_to_id = {}

    def next_unique(self):
        return next(self.counter)

    def next_with_nonce(self, nonce: object):
        if nonce not in self.nonce_to_id:
            self.nonce_to_id[nonce] = next(self.counter)
        return self.nonce_to_id[nonce]


def serialize_subvol(subvol, path=b'.', gen=None):
    if gen is None:
        gen = FakeInodeIds()
    ino_id = subvol.id_map.get_id(path)
    ino_repr = (repr(subvol.id_to_inode[ino_id]), gen.next_with_nonce(ino_id))
    children = subvol.id_map.get_children(ino_id)
    if not children:
        return ino_repr
    return (ino_repr, {
        os.path.relpath(child_path, path).decode(errors='surrogateescape'):
            serialize_subvol(subvol, child_path, gen)
                # The order must match `serialized_subvol_add_fake_inode_ids`
                for child_path in sorted(children)
    })


def serialized_subvol_add_fake_inode_ids(ser, gen: FakeInodeIds=None):
    if gen is None:
        gen = FakeInodeIds()
    if isinstance(ser, InodeRepr):  # precedes `tuple` since it's a NamedTuple
        return (ser.ino_repr, gen.next_with_nonce(ser))
    elif isinstance(ser, tuple):
        ino_repr, children = ser
        return (serialized_subvol_add_fake_inode_ids(ino_repr, gen), {
            path: serialized_subvol_add_fake_inode_ids(child_repr, gen)
                # Traverse children in the same order as `serialize_subvol`
                # so that fake inode IDs are guaranteed to agree.
                for path, child_repr in sorted(children.items())
        })
    elif isinstance(ser, str):
        return (ser, gen.next_unique())
    raise AssertionError(f'Unknown {ser}')
