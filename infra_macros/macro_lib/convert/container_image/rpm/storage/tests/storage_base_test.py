#!/usr/bin/env python3
import unittest

from typing import List

from .. import Storage  # Module import to ensure we get plugins


class StorageBaseTestCase(unittest.TestCase):
    'A tiny test suite that can be used to check any Storage implementation.'

    def _write_and_read(self, storage: Storage, writes: List[bytes]):
        with storage.writer() as output:
            for piece in writes:
                output.write(piece)
        with storage.reader(output.id) as input:
            self.assertEqual(b''.join(writes), input.read())
        return output.id

    def _check_write_and_read_back(
        self,
        storage: Storage, *,
        no_empty_blobs=False,
        skip_empty_writes=False,
        # To make testing more meaningful, it's useful to make sure that
        # some writes fill up any output buffers.  For filesystem writes
        # from Python, this default is probably enough.
        mul=314159,  # just about 300KB
    ):
        for writes in [
            # Some large writes
            [b'abcd' * mul, b'efgh' * mul],
            [b'abc' * mul, b'defg' * mul],
            [b'abc' * mul, b'def' * mul, b'g' * mul],
            [b'abcd' * mul],
            [b'abc' * mul, b'd' * mul],
            # Some tiny writes without a multiplier
            [b'a', b'b', b'c', b'd'],
            [b'ab'],
            [b'a', b'b'],
            # While clowny, some blob storage systems refuse empty blobs.
            *([] if no_empty_blobs else [
                [b''],
                [],
            ]),
        ]:
            # Test the given writes, optionally insert a blank at each index
            for i in [
                None,
                *([] if skip_empty_writes else range(len(writes) + 1)),
            ]:
                yield writes, self._write_and_read(
                    storage,
                    writes if i is None else [*writes[:i], b'', *writes[i:]],
                )
