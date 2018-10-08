#!/usr/bin/env python3
'Utilities to make Python systems programming more palatable.'
import hashlib
import logging
import os
import subprocess
import stat

from typing import AnyStr, NamedTuple


def init_logging(*, debug: bool=False):
    logging.basicConfig(
        format='%(levelname)s %(name)s %(asctime)s %(message)s',
        level=logging.DEBUG if debug else logging.INFO,
    )


# Bite me, Python3.
def byteme(s: AnyStr) -> bytes:
    'Byte literals are tiring, just promote strings as needed.'
    return s.encode() if isinstance(s, str) else s


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


def open_ro(path, mode):
    '`open` that creates (and never overwrites) a file with mode `a+r`.'
    def ro_opener(path, flags):
        return os.open(
            path,
            (flags & ~os.O_TRUNC) | os.O_CREAT | os.O_CLOEXEC,
            mode=stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
        )
    return open(path, mode, opener=ro_opener)


def set_new_key(d, k, v):
    '`d[k] = v` that raises if it would it would overwrite an existing value'
    if k in d:
        raise KeyError(f'{k} was already set')
    d[k] = v


def check_popen_returncode(proc: subprocess.Popen):
    if proc.returncode != 0:  # pragma: no cover
        # Providing a meaningful coverage test for this is annoying, so I just
        # tested manually:
        #   >>> import subprocess
        #   >>> raise subprocess.CalledProcessError(returncode=5, cmd=['a'])
        #   Traceback (most recent call last):
        #     File "<stdin>", line 1, in <module>
        #   subprocess.CalledProcessError: Command '['a']' returned non-zero
        #   exit status 5.
        raise subprocess.CalledProcessError(
            returncode=proc.returncode, cmd=proc.args,
        )


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
