#!/usr/bin/env python3
import hashlib
import subprocess

from typing import NamedTuple


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
