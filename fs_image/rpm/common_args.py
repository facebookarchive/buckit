#!/usr/bin/env python3
'Arguments shared between `snapshot-repo` and `snapshot-repos`.'
from .common import RpmShard
from .storage import Storage
from .db_connection import DBConnectionContext


# BEWARE: If your script calls this helper, it is responsible for supporting
# **all** of its arguments.  Just go through the code and make sure that
# each one is accessed appropriately.
def add_standard_args(parser):
    parser.add_argument(  # Pass this to `populate_temp_dir_and_rename`
        '--snapshot-dir', required=True,
        help='Create or overwrite an RPM repo snapshot at this location. '
            'This consists of top-level repo metadata plus JSON indexes '
            'that provide `storage_id`s for the large binary blobs, which '
            'are actually written to `--storage`. The snapshot is meant '
            'to be committed into a version-control system, so it is concise '
            'and textual.',
    )
    Storage.add_argparse_arg(  # Pass this to `RepoDownloader`
        parser, '--storage', required=True,
        help='Where to store large binary blobs like RPMs and repo indexes. ',
    )
    DBConnectionContext.add_argparse_arg(  # Pass this to `RepoDBContext`
        parser, '--db', required=True,
        help='This database contains the same type of information as '
            '--snapshot-dir, but persisted across multiple runs to make '
            'incremental snapshots very fast. The DB also permits multiple '
            'writers to concurrently upload blobs to `--storage` -- see '
            'e.g. `--rpm-shard`. ',
    )
    parser.add_argument(  # Pass this to `RepoDownloader`
        '--rpm-shard',
        default='0:1', metavar='SHARD:MOD', type=RpmShard.from_string,
        help='Only fetch RPMs whose filenames hash to SHARD modulo MOD. '
            'Good for parallel downloads, or for quick-iteration testing. '
            'Defaults to downloading all RPMs.',
    )
    parser.add_argument(  # E.g. for `retry_fn` as `delays=[0] * args.retries`
        '--retries', default=10, type=int,
        help='How many times per repo to retry downloading + writing to '
            '--storage and --db (writes to --snapshot-dir are not retried). '
            'Use a reasonably high value -- failures are normal. For example, '
            'if we race with any repo change, we are liable to get HTTP 404 '
            'for deleted repodata objects.',
    )
    parser.add_argument(  # Pass this to `init_logging`
        '--debug', action='store_true',
        help='Should we print debug log messages?',
    )
