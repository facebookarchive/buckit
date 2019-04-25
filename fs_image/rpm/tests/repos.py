#!/usr/bin/env python3
from libfb.py.fbcode_root import get_fbcode_dir
import os
import os.path


def get_test_repos_path() -> 'os.PathLike[str]':
    return os.path.join(get_fbcode_dir(), 'fs_image/rpm/tests/repos')
