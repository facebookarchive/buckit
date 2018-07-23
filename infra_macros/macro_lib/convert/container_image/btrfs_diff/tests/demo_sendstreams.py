#!/usr/bin/env python3
'''Helpers to access the results of make_demo_sendstreams.py'''
import os
import pickle
import subprocess

from artifacts_dir import ensure_per_repo_artifacts_dir_exists


def sibling_path(rel_path):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)


def make_demo_sendstreams(path_in_repo):
    'Run `make_demo_sendstreams.py` under `sudo`, unpickle the result.'
    return pickle.loads(subprocess.run(
        # We depend on a hierarchy of this sort:
        #   .:
        #   artifacts_dir.py volume_for_repo.py
        #
        #   ./btrfs_diff/tests:
        #   demo_sendstreams.py
        [
            'sudo',
            'PYTHONDONTWRITEBYTECODE=1',  # Avoid root-owned .pyc in buck-out/
            sibling_path('make-demo-sendstreams'),
            '--print', 'pickle',
            # We want to create this directory as an unprivileged user, so
            # create it before the `sudo`.  Without this, we could end up
            # unable to write the garbage-collection metadata -- `root` only
            # manages the subvolume directories themselves.
            '--artifacts-dir',
            ensure_per_repo_artifacts_dir_exists(path_in_repo),
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        stdout=subprocess.PIPE, check=True,
    ).stdout)


def gold_demo_sendstreams():
    with open(sibling_path('gold_demo_sendstreams.pickle'), 'rb') as f:
        return pickle.load(f)
