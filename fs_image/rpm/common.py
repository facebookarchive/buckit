#!/usr/bin/env python3
'Utilities to make Python systems programming more palatable.'
import hashlib
import os
import stat
import struct

from typing import AnyStr, NamedTuple

# Hide the fact that some of our dependencies aren't in `rpm` any more, the
# `rpm` library still imports them from `rpm.common`.
from fs_image.common import (  # noqa: F401
    byteme, check_popen_returncode, get_file_logger, init_logging,
)

_UINT64_STRUCT = struct.Struct('=Q')


# `pathlib` refuses to operate on `bytes`, which is the only sane way on Linux.
class Path(bytes):
    'A byte path that supports joining via the / operator.'

    def __new__(cls, arg, *args, **kwargs):
        return super().__new__(cls, byteme(arg), *args, **kwargs)

    def __truediv__(self, right: AnyStr) -> bytes:
        return Path(os.path.join(self, byteme(right)))

    def __rtruediv__(self, left: AnyStr) -> bytes:
        return Path(os.path.join(byteme(left), self))

    def decode(self):  # Future: add other args as needed.
        # Python uses `surrogateescape` when the filesystem contains invalid
        # utf-8. Test:
        #   $ mkdir -p test/$'\xc3('
        #   $ python3 -c 'import os;print(os.listdir("test"))'
        #   ['\udcc3(']
        return super().decode(errors='surrogateescape')

    @classmethod
    def from_argparse(cls, s: str) -> 'Path':
        # Python uses `surrogateescape` for `sys.argv`. Test:
        #   $ python3 -c 'import sys;print(repr(sys.argv[1]),' \
        #       'repr(sys.argv[1].encode(errors="surrogateescape")))' $'\xc3('
        #   '\udcc3(' b'\xc3('
        return Path(s.encode(errors='surrogateescape'))


def create_ro(path, mode):
    '`open` that creates (and never overwrites) a file with mode `a+r`.'
    def ro_opener(path, flags):
        return os.open(
            path,
            (flags & ~os.O_TRUNC) | os.O_CREAT | os.O_CLOEXEC,
            mode=stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
        )
    return open(path, mode, opener=ro_opener)


class RpmShard(NamedTuple):
    '''
    Used for testing, or for splitting a snapshot into parallel processes.
    In the latter case, each snapshot will redundantly fetch & store the
    metadata, so don't go overboard with the number of shards.
    '''
    shard: int
    modulo: int

    @classmethod
    def from_string(cls, shard_name: str) -> 'RpmShard':
        shard, mod = (int(v) for v in shard_name.split(':'))
        assert 0 <= shard < mod, f'Bad RPM shard: {shard_name}'
        return RpmShard(shard=shard, modulo=mod)

    def in_shard(self, rpm):
        # Our contract is that the RPM filename is the global primary key,
        #
        # We use the last 8 bytes of SHA1, since we need a deterministic
        # hash for parallel downloads, and Python standard library lacks
        # fast non-cryptographic hashes like CityHash or SpookyHashV2.
        # adler32 is faster, but way too collision-prone to bother.
        h, = _UINT64_STRUCT.unpack_from(
            hashlib.sha1(byteme(rpm.filename())).digest(), 12
        )
        return h % self.modulo == self.shard


class Checksum(NamedTuple):
    algorithm: str
    hexdigest: str

    @classmethod
    def from_string(cls, s: str) -> 'Checksum':
        algorithm, hexdigest = s.split(':')
        return cls(algorithm=algorithm, hexdigest=hexdigest)

    def __str__(self):
        return f'{self.algorithm}:{self.hexdigest}'

    def hasher(self):
        # Certain repos use "sha" to refer to "SHA-1", whereas in `hashlib`,
        # "sha" goes through OpenSSL and refers to a different digest.
        if self.algorithm == 'sha':
            return hashlib.sha1()
        return hashlib.new(self.algorithm)
