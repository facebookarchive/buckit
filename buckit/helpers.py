from contextlib import contextmanager
import errno
import fcntl
import time


class BuckitException(Exception):
    """
    Superclass for buckit exceptions that also formats messages by default
    """

    def __init__(self, message, *formatargs, **formatkwargs):
        super(BuckitException, self).__init__(
            message.format(*formatargs, **formatkwargs))


@contextmanager
def open_with_lock(filename, mode):
    with open(filename, mode) as f:
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                yield f
                break
            except IOError as e:
                # raise on unrelated IOErrors
                if e.errno != errno.EAGAIN:
                    raise
                else:
                    time.sleep(0.1)
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
