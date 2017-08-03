from contextlib import contextmanager
import fcntl


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
    except:
        pass
