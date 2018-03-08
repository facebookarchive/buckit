#!/usr/bin/env python3
import unittest

from ..subvol_path import SubvolPath


class SubvolPathTestCase(unittest.TestCase):

    def test_repr(self):
        self.assertEqual("SubvolPath._new(b'a')", repr(SubvolPath._new(b'a')))
        self.assertEqual(
            "SubvolPath._new(b'x/y/z')", repr(SubvolPath._new(b'x/y/z')),
        )

    def test_bytes(self):
        self.assertEqual(b'a', bytes(SubvolPath._new(b'a')))
        self.assertEqual(b'x/y/z', bytes(SubvolPath._new(b'x/y/z')))

    def test_new(self):
        self.assertEqual(
            SubvolPath(subvol=b'a', path=None),
            SubvolPath._new(b'a'),
        )
        self.assertEqual(
            SubvolPath(subvol=b'x', path=b'y/z'),
            SubvolPath._new(b'x///y/z/'),  # Ensure we normalize paths
        )


if __name__ == '__main__':
    unittest.main()
