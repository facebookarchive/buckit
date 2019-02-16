#!/usr/bin/env python3
'Utilities to make Python systems programming more palatable.'
import logging
import os
import subprocess

from typing import AnyStr, Iterable
from contextlib import AbstractContextManager, contextmanager


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


# contextlib.nullcontext is 3.7+ but we are on 3.6 for now. This has to be a
# class since it should be multi-use.
class nullcontext(AbstractContextManager):

    def __init__(self, val=None):
        self._val = val

    def __enter__(self):
        return self._val

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None  # Do not suppress exceptions


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


def run_stdout_to_err(
    args: Iterable[AnyStr], *, stdout: None=None, **kwargs
) -> subprocess.CompletedProcess:
    '''
    Use this instead of `subprocess.{run,call,check_call}()` to prevent
    subprocesses from accidentally polluting stdout.
    '''
    assert stdout is None, 'run_stdout_to_err does not take a stdout kwarg'
    return subprocess.run(args, **kwargs, stdout=2)  # Redirect to stderr


@contextmanager
def pipe():
    r_fd, w_fd = os.pipe2(os.O_CLOEXEC)
    with os.fdopen(r_fd, 'rb') as r, os.fdopen(w_fd, 'wb') as w:
        yield r, w
