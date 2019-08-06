#!/usr/bin/env python3
'Utilities to make Python systems programming more palatable.'
import errno
import hashlib
import os
import shutil
import stat
import struct
import time
import tempfile

from contextlib import contextmanager
from typing import AnyStr, Callable, Iterable, List, NamedTuple, TypeVar

# Hide the fact that some of our dependencies aren't in `rpm` any more, the
# `rpm` library still imports them from `rpm.common`.
from fs_image.common import (  # noqa: F401
    byteme, check_popen_returncode, get_file_logger, init_logging,
)

log = get_file_logger(__file__)
_UINT64_STRUCT = struct.Struct('=Q')
T = TypeVar('T')


# `pathlib` refuses to operate on `bytes`, which is the only sane way on Linux.
class Path(bytes):
    'A byte path that supports joining via the / operator.'

    def __new__(cls, arg, *args, **kwargs):
        return super().__new__(cls, byteme(arg), *args, **kwargs)

    def __truediv__(self, right: AnyStr) -> 'Path':
        return Path(os.path.join(self, byteme(right)))

    def __rtruediv__(self, left: AnyStr) -> 'Path':
        return Path(os.path.join(byteme(left), self))

    def basename(self) -> 'Path':
        return Path(os.path.basename(self))

    def dirname(self) -> 'Path':
        return Path(os.path.dirname(self))

    def decode(self) -> str:  # Future: add other args as needed.
        # Python uses `surrogateescape` for invalid UTF-8 from the filesystem.
        return super().decode(errors='surrogateescape')

    @classmethod
    def from_argparse(cls, s: str) -> 'Path':
        # Python uses `surrogateescape` for `sys.argv`.
        return Path(s.encode(errors='surrogateescape'))


@contextmanager
def temp_dir(**kwargs) -> Iterable['Path']:
    with tempfile.TemporaryDirectory(**kwargs) as td:
        yield Path(td)


def create_ro(path, mode):
    '`open` that creates (and never overwrites) a file with mode `a+r`.'
    def ro_opener(path, flags):
        return os.open(
            path,
            (flags & ~os.O_TRUNC) | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            mode=stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
        )
    return open(path, mode, opener=ro_opener)


@contextmanager
def populate_temp_dir_and_rename(dest_path, overwrite=False) -> Path:
    '''
    Returns a Path to a temporary directory. The context block may populate
    this directory, which will then be renamed to `dest_path`, optionally
    deleting any preexisting directory (if `overwrite=True`).

    If the context block throws, the partially populated temporary directory
    is removed, while `dest_path` is left alone.

    By writing to a brand-new temporary directory before renaming, we avoid
    the problems of partially writing files, or overwriting some files but
    not others.  Moreover, populate-temporary-and-rename is robust to
    concurrent writers, and tends to work on broken NFSes unlike `flock`.
    '''
    dest_path = os.path.normpath(dest_path)  # Trailing / breaks `os.rename()`
    # Putting the temporary directory as a sibling minimizes permissions
    # issues, and maximizes the chance that we're on the same filesystem
    base_dir = os.path.dirname(dest_path)
    td = tempfile.mkdtemp(dir=base_dir)
    try:
        yield Path(td)

        # Delete+rename is racy, but EdenFS lacks RENAME_EXCHANGE (t34057927)
        # Retry if we raced with another writer -- i.e., last-to-run wins.
        while True:
            if overwrite and os.path.isdir(dest_path):
                with tempfile.TemporaryDirectory(dir=base_dir) as del_dir:
                    try:
                        os.rename(dest_path, del_dir)
                    except FileNotFoundError:  # pragma: no cover
                        continue  # retry, another writer deleted first?
            try:
                os.rename(td, dest_path)
            except OSError as ex:
                if not (overwrite and ex.errno in [
                    # Different kernels have different error codes when the
                    # target already exists and is a nonempty directory.
                    errno.ENOTEMPTY, errno.EEXIST,
                ]):
                    raise
                log.exception(  # pragma: no cover
                    f'Retrying deleting {dest_path}, another writer raced us'
                )
            break  # We won the race
    except BaseException:
        shutil.rmtree(td)
        raise


def retry_fn(
    fn: Callable[[], T], *, delays: List[float] = None, what: str,
) -> T:
    'Delays are in seconds.'
    for i, delay in enumerate(delays):
        try:
            return fn()
        except Exception:
            log.exception(
                f'\n\n[Retry {i + 1} of {len(delays)}] {what} -- waiting '
                f'{delay} seconds.\n\n'
            )
            time.sleep(delay)
    return fn()  # With 0 retries, we should still run the function.


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
