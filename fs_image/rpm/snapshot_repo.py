#!/usr/bin/env python3
'''
`snapshot-repo` is mostly intended for testing downloads of a single repo.
In production, you will usually want `snapshot-repos`, which will snapshot
all repos from a given `yum.conf`.
'''
import argparse
import sys

from .common import (
    get_file_logger, init_logging, populate_temp_dir_and_rename, retry_fn,
)
from .common_args import add_standard_args
from .repo_db import RepoDBContext
from .repo_downloader import RepoDownloader
from .repo_sizer import RepoSizer

log = get_file_logger(__file__)


def snapshot_repo(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_standard_args(parser)
    parser.add_argument(
        '--repo-name', required=True,
        help="Used to distinguish this repo's metadata from others' in the DB.",
    )
    parser.add_argument(
        '--repo-url', required=True,
        help='The base URL of the repo -- the part before repodata/repomd.xml. '
            'Supported protocols include file://, https://, and http://.',
    )
    args = parser.parse_args(argv)

    init_logging(debug=args.debug)

    with populate_temp_dir_and_rename(args.snapshot_dir, overwrite=True) as td:
        sizer = RepoSizer()
        retry_fn(
            lambda: RepoDownloader(
                args.repo_name,
                args.repo_url,
                RepoDBContext(args.db, args.db.SQL_DIALECT),
                args.storage,
            ).download(rpm_shard=args.rpm_shard),
            delays=[0] * args.retries,
            what=f'Downloading {args.repo_name} from {args.repo_url} failed',
        ).visit(sizer).to_directory(td)
        log.info(sizer.get_report(f'This {args.rpm_shard} snapshot weighs'))


if __name__ == '__main__':  # pragma: no cover
    snapshot_repo(sys.argv[1:])
