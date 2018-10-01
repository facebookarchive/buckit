#!/usr/bin/env python3
import os
import itertools
import json
import tempfile

from collections import Counter

from .storage_base_test import Storage, StorageBaseTestCase


class FilesystemStorageTestCase(StorageBaseTestCase):
    def test_write_and_read_back(self):
        expected_content_count = Counter()
        with tempfile.TemporaryDirectory() as td:
            storage = Storage.make(
                **Storage.parse_config(json.dumps({
                    'name': 'filesystem', 'base_dir': td,
                })),
            )

            for writes, _ in self._check_write_and_read_back(storage):
                expected_content_count[b''.join(writes)] += 1

            # Make a histogram of the contents of the output files
            content_count = Counter()
            for f in itertools.chain.from_iterable(
                [os.path.join(p, f) for f in fs]
                    for p, _, fs in os.walk(storage.base_dir) if fs
            ):
                with open(f, 'rb') as infile:
                    content_count[infile.read()] += 1

            # Did we produce the expected number of each kind of output?
            self.assertEqual(expected_content_count, content_count)
