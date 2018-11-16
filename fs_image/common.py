#!/usr/bin/env python3
'Utilities to make Python systems programming more palatable.'
import logging
import os
import subprocess

from typing import AnyStr


# Bite me, Python3.
def byteme(s: AnyStr) -> bytes:
    'Byte literals are tiring, just promote strings as needed.'
    return s.encode() if isinstance(s, str) else s


def get_file_logger(py_path: AnyStr):
    return logging.getLogger(os.path.basename(py_path))


def init_logging(*, debug: bool=False):
    logging.basicConfig(
        format='%(levelname)s %(name)s %(asctime)s %(message)s',
        level=logging.DEBUG if debug else logging.INFO,
    )


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
