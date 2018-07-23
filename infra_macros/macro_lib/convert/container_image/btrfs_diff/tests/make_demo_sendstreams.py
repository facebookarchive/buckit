#!/usr/bin/env python3
'''
Prints a pickled dict of test data to stdout. Must be run as `root`.
This is **not** a library, import from `demo_sendstreams.py` in unit-tests.

Note that this will not work under system Python directly (unless
`libbtrtfsutil` is available), so prefer to `buck run` the corresponding
target.

The intent of this script is to exercise all the send-stream command types
that can be emitted by `btrfs send`.

After running from inside the per-Buck-repo btrfs volume,
`test_parse_dump.py` and `test_parse_send_stream.py` compare the parsed
output to what we expect on the basis of this script.

For usage, `buck run .../btrfs_diff:tests-make-demo-sendstreams -- --help`.

## Updating this script's gold output

Run this:

  sudo REPO_ROOT/buck-out/gen/.../btrfs_diff/tests-make-demo-sendstreams* \\
    --write-gold-to-dir btrfs_diff/tests/ \\
    --artifacts-dir "$(buck run ...:artifacts-dir)"

You will then need to manually update `uuid_create` and related fields in
the "expected" section of the test.

In addition to parsing the gold output, `test_parse_dump.py` also checks
that we are able to parse the output of a **live** `btrfs receive --dump`.
Unfortunately, we are not able to check the **correctness** of these live
parses.  This is because the specific sequence of lines that `btrfs send`
produces to represent the filesystem is an implementation detail without a
_uniquely_ correct output, which may change over time.

Besides testing that parsing does not crash on a live `demo_sendstreams.py`,
whose output may even vary from host-to-host, we do two things:

 - Via this script, we freeze a sequence from one point in time just for the
   sake of having a parse-only test.

 - To test the semantics of the parsed data, we test applying a freshly
   generated sendstream to a mock filesystem, which should always give the
   same result, regardless of the specific send-stream commands used.
'''
import os
import argparse
import contextlib
import enum
import pickle
import pprint
import socket
import subprocess
import tempfile
import time

from typing import Tuple

from volume_for_repo import get_volume_for_current_repo

from .btrfs_utils import (
    CheckedRunTemplate, mark_subvolume_readonly_and_get_sendstream,
    TempSubvolumes, RelativePath,
)


def make_create_ops_subvolume(subvols: TempSubvolumes, path: RelativePath):
    'Exercise all the send-stream ops that can occur on a new subvolume.'
    subvols.create(path())
    run = CheckedRunTemplate(cwd=path())

    # Due to an odd `btrfs send` implementation detail, creating a file or
    # directory emits a rename from a temporary name to the final one.
    run('mkdir', 'hello')                           # mkdir,rename
    run('mkdir', 'dir_to_remove')
    run('touch', 'hello/world')                     # mkfile,utimes,chmod,chown
    run(                                            # set_xattr
        'setfattr', '-n', 'user.test_attr', '-v', 'chickens', 'hello/',
    )
    run('mknod', 'buffered', 'b', 1337, 31415)      # mknod
    run('chmod', 'og-r', 'buffered')                # chmod a device
    run('mknod', 'unbuffered', 'c', 1337, 31415)
    run('mkfifo', 'fifo')                           # mkfifo
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        # Hack to avoid "AF_UNIX path too long"
        old_cwd = os.getcwd()
        try:
            os.chdir(path())
            sock.bind('unix_sock')                  # mksock
        finally:
            os.chdir(old_cwd)
    run('ln', 'hello/world', 'goodbye')             # link
    run('ln', '-s', 'hello/world', 'bye_symlink')   # symlink
    run(                                            # update_extent
        'dd', 'if=/dev/zero', 'of=1MB_nuls', 'bs=1024', 'count=1024',
    )
    run(                                            # clone
        'cp', '--reflink=always', '1MB_nuls', '1MB_nuls_clone',
    )

    # Make a file with a 16KB hole in the middle.
    run(
        'dd', 'if=/dev/zero', 'of=zeros_hole_zeros', 'bs=1024', 'count=16',
    )
    run('truncate', '-s', 32 * 1024, 'zeros_hole_zeros')
    with open(path('zeros_hole_zeros'), 'ab') as f:
        f.write(b'\0' * (16 * 1024))

    # This just serves to show that `btrfs send` ignores nested subvolumes.
    # There is no mention of `nested_subvol` in the send-stream.
    subvols.create(path('nested_subvol'))
    run2 = CheckedRunTemplate(cwd=path('nested_subvol'))
    run2('touch', 'borf')
    run2('mkdir', 'beep')


def make_mutate_ops_subvolume(
    subvols: TempSubvolumes, create_ops_rel: RelativePath, path: RelativePath,
):
    'Exercise the send-stream ops that are unique to snapshots.'
    subvols.snapshot(create_ops_rel(), path())     # snapshot
    run = CheckedRunTemplate(cwd=path())

    run('rm', 'hello/world')                        # unlink
    run('rmdir', 'dir_to_remove/')                  # rmdir
    run(                                            # remove_xattr
        'setfattr', '--remove=user.test_attr', 'hello/',
    )
    # You would think this would emit a `rename`, but for files, the
    # sendstream instead `link`s to the new location, and unlinks the old.
    run('mv', 'goodbye', 'farewell')                # NOT a rename... {,un}link
    run('mv', 'hello/', 'hello_renamed/')           # yes, a rename!
    with open(path('hello_renamed/een'), 'w') as f:
        f.write('push\n')                           # write
    # This is a no-op because `btfs send` does not support `chattr` at
    # present.  However, it's good to have a canary so that our tests start
    # failing the moment it is supported -- that will remind us to update
    # the mock VFS.  NB: The absolute path to `chattr` is a clowny hack to
    # work around a clowny hack, to work around clowny hacks.  Don't ask.
    run('/usr/bin/chattr', '+a', 'hello_renamed/een')


def float_to_sec_nsec_tuple(t: float) -> Tuple[int, int]:
    sec = int(t)
    return (sec, int(1e9 * (t - sec)))


@contextlib.contextmanager
def populate_sendstream_dict(d):
    d['build_start_time'] = float_to_sec_nsec_tuple(time.time())
    yield d
    d['dump'] = subprocess.run(
        ['btrfs', 'receive', '--dump'],
        input=d['sendstream'], stdout=subprocess.PIPE, check=True,
        # split into lines to make the `pretty` output prettier
    ).stdout.rstrip(b'\n').split(b'\n')
    d['build_end_time'] = float_to_sec_nsec_tuple(time.time())


def demo_sendstreams(temp_dir: bytes):
    with TempSubvolumes() as subvols:
        res = {}

        create_ops_rel = RelativePath(temp_dir, 'create_ops')
        with populate_sendstream_dict(res.setdefault('create_ops', {})) as d:
            make_create_ops_subvolume(subvols, create_ops_rel)
            d['sendstream'] = mark_subvolume_readonly_and_get_sendstream(
                create_ops_rel(), send_args=['--no-data'],
            )

        mutate_ops_rel = RelativePath(temp_dir, 'mutate_ops')
        with populate_sendstream_dict(res.setdefault('mutate_ops', {})) as d:
            make_mutate_ops_subvolume(subvols, create_ops_rel, mutate_ops_rel)
            d['sendstream'] = mark_subvolume_readonly_and_get_sendstream(
                mutate_ops_rel(), send_args=['-p', create_ops_rel()],
            )

        return res


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    class Print(enum.Enum):
        NONE = 'none'
        PRETTY = 'pretty'
        PICKLE = 'pickle'

        def __str__(self):
            return self.value

    p.add_argument(
        '--print', type=Print, choices=Print, default=Print.NONE,
        help='If set, prints the result in the specified format to stdout.',
    )
    p.add_argument(
        '--write-gold-to-dir',
        help='If set, writes the gold test data into the given directory as '
            'gold_demo_sendstreams.{pickle,pretty}. Warning: you will need '
            'to manually update some constants like `uuid_create` in the '
            '"expected" section of the test code.',
    )
    p.add_argument(
        '--artifacts-dir', required=True,
        help='Pass $(artifacts_dir.py) to ensure it is not owned by root',
    )
    args = p.parse_args()

    with tempfile.TemporaryDirectory(
        dir=get_volume_for_current_repo(1e8, args.artifacts_dir),
    ) as temp_dir:
        sendstream_dict = demo_sendstreams(temp_dir)
        # This width makes the `--dump`ed commands fit on one line.
        prettified = pprint.pformat(sendstream_dict, width=200).encode()
        pickled = pickle.dumps(sendstream_dict)

        if args.print == Print.PRETTY:
            real_binary_stdout.write(prettified)
        elif args.print == Print.PICKLE:
            real_binary_stdout.write(pickled)
        else:
            assert args.print == Print.NONE, args.print

        if args.write_gold_to_dir is not None:
            for filename, data in [
                ('gold_demo_sendstreams.pickle', pickled),
                ('gold_demo_sendstreams.pretty', prettified),  # For humans
            ]:
                path = os.path.join(args.write_gold_to_dir, filename)
                # We want these files to be created by a non-root user
                assert os.path.exists(path), path
                with open(path, 'wb') as f:
                    f.write(data)


if __name__ == '__main__':
    # Replace stdout by stderr to prevent random `btrfs-progs` utilities
    # from rendering our pickled stdout unreadable.
    #
    # Do this FIRST, before any stdout writes might happen, or we'll make a
    # mess of Python's internal buffering.
    #
    # Future: remove once `btrfsutil` can completely replace the `btrfs` CLI.
    with os.fdopen(os.dup(1), 'wb') as real_binary_stdout:
        os.dup2(2, 1)
        main()
