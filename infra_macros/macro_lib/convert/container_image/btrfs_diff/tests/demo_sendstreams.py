#!/usr/bin/env python3
'''
Prints a pickled dict of test data to stdout. As a binary, does NOT work
in @mode/opt -- in that role, it's just a development tool.

The intent of this script is to exercise all the send-stream command types
that can be emitted by `btrfs send`.

After running from inside the per-Buck-repo btrfs volume,
`test_parse_dump.py` and `test_parse_send_stream.py` compare the parsed
output to what we expect on the basis of this script.

For usage, `buck run .../btrfs_diff:make-demo-sendstreams -- --help`.

## Updating this script's gold output

Run this:

  buck run .../btrfs_diff:make-demo-sendstreams* \\
    --write-gold-to-dir btrfs_diff/tests/

You will then need to manually update `uuid_create` and related fields in
the "expected" section of the test.

In addition to parsing the gold output, `test_parse_dump.py` also checks
that we are able to parse the output of a **live** `btrfs receive --dump`.
Unfortunately, we are not able to check the **correctness** of these live
parses.  This is because the specific sequence of lines that `btrfs send`
produces to represent the filesystem is an implementation detail without a
_uniquely_ correct output, which may change over time.

Besides testing that parsing does not crash on a live `make_demo_sendstreams`,
whose output may even vary from host-to-host, we do two things:

 - Via this script, we freeze a sequence from one point in time just for the
   sake of having a parse-only test.

 - To test the semantics of the parsed data, we test applying a freshly
   generated sendstream to a mock filesystem, which should always give the
   same result, regardless of the specific send-stream commands used.
'''
#
# Note: When used as a library (through functions not prefixed with
# underscore), this code needs to work in @mode/opt, and so should not
# assume it has unfettered access to the source repo.
#
import os
import argparse
import contextlib
import enum
import pickle
import pprint
import subprocess
import sys
import time

from functools import partial
from typing import Tuple

from artifacts_dir import ensure_per_repo_artifacts_dir_exists
from volume_for_repo import get_volume_for_current_repo

from .btrfs_utils import Subvol, TempSubvolumes


def _make_create_ops_subvolume(subvols: TempSubvolumes, path: bytes) -> Subvol:
    'Exercise all the send-stream ops that can occur on a new subvolume.'
    subvol = subvols.create(path)
    run = partial(subvol.run_as_root, cwd=subvol.path())

    # Due to an odd `btrfs send` implementation detail, creating a file or
    # directory emits a rename from a temporary name to the final one.
    run(['mkdir', 'hello'])                         # mkdir,rename
    run(['mkdir', 'dir_to_remove'])
    run(['touch', 'hello/world'])                   # mkfile,utimes,chmod,chown
    run([                                           # set_xattr
        'setfattr', '-n', 'user.test_attr', '-v', 'chickens', 'hello/',
    ])
    run(['mknod', 'buffered', 'b', '1337', '31415'])  # mknod
    run(['chmod', 'og-r', 'buffered'])              # chmod a device
    run(['mknod', 'unbuffered', 'c', '1337', '31415'])
    run(['mkfifo', 'fifo'])                         # mkfifo
    run(['python3', '-c', (
        'import socket as s\n'
        'with s.socket(s.AF_UNIX, s.SOCK_STREAM) as sock:\n'
        '    sock.bind("unix_sock")\n'              # mksock
    )])
    run(['ln', 'hello/world', 'goodbye'])           # link
    run(['ln', '-s', 'hello/world', 'bye_symlink'])  # symlink
    run([                                           # update_extent
        'dd', 'if=/dev/zero', 'of=1MB_nuls', 'bs=1024', 'count=1024',
    ])
    run([                                           # clone
        'cp', '--reflink=always', '1MB_nuls', '1MB_nuls_clone',
    ])

    # Make a file with a 16KB hole in the middle.
    run(['dd', 'if=/dev/zero', 'of=zeros_hole_zeros', 'bs=1024', 'count=16'])
    run(['truncate', '-s', str(32 * 1024), 'zeros_hole_zeros'])
    run([
        'dd', 'if=/dev/zero', 'of=zeros_hole_zeros',
        'oflag=append', 'conv=notrunc', 'bs=1024', 'count=16',
    ])

    # This just serves to show that `btrfs send` ignores nested subvolumes.
    # There is no mention of `nested_subvol` in the send-stream.
    nested_subvol = subvols.create(subvol.path(b'nested_subvol'))
    run2 = partial(nested_subvol.run_as_root, cwd=nested_subvol.path())
    run2(['touch', 'borf'])
    run2(['mkdir', 'beep'])

    return subvol


def _make_mutate_ops_subvolume(
    subvols: TempSubvolumes, create_ops: Subvol, path: bytes,
) -> Subvol:
    'Exercise the send-stream ops that are unique to snapshots.'
    subvol = subvols.snapshot(create_ops, path)       # snapshot
    run = partial(subvol.run_as_root, cwd=subvol.path())

    run(['rm', 'hello/world'])                        # unlink
    run(['rmdir', 'dir_to_remove/'])                  # rmdir
    run([                                             # remove_xattr
        'setfattr', '--remove=user.test_attr', 'hello/',
    ])
    # You would think this would emit a `rename`, but for files, the
    # sendstream instead `link`s to the new location, and unlinks the old.
    run(['mv', 'goodbye', 'farewell'])                # NOT a rename, {,un}link
    run(['mv', 'hello/', 'hello_renamed/'])           # yes, a rename!
    run(                                              # write
        ['dd', 'of=hello_renamed/een'], input=b'push\n',
    )
    # This is a no-op because `btfs send` does not support `chattr` at
    # present.  However, it's good to have a canary so that our tests start
    # failing the moment it is supported -- that will remind us to update
    # the mock VFS.  NB: The absolute path to `chattr` is a clowny hack to
    # work around a clowny hack, to work around clowny hacks.  Don't ask.
    run(['/usr/bin/chattr', '+a', 'hello_renamed/een'])

    return subvol


def _float_to_sec_nsec_tuple(t: float) -> Tuple[int, int]:
    sec = int(t)
    return (sec, int(1e9 * (t - sec)))


@contextlib.contextmanager
def _populate_sendstream_dict(d):
    d['build_start_time'] = _float_to_sec_nsec_tuple(time.time())
    yield d
    d['dump'] = subprocess.run(
        ['btrfs', 'receive', '--dump'],
        input=d['sendstream'], stdout=subprocess.PIPE, check=True,
        # split into lines to make the `pretty` output prettier
    ).stdout.rstrip(b'\n').split(b'\n')
    d['build_end_time'] = _float_to_sec_nsec_tuple(time.time())


def _make_demo_sendstreams(temp_dir: bytes):
    with TempSubvolumes() as subvols:
        res = {}

        with _populate_sendstream_dict(res.setdefault('create_ops', {})) as d:
            create_ops = _make_create_ops_subvolume(
                subvols, os.path.join(temp_dir, b'create_ops'),
            )
            d['sendstream'] = create_ops.get_sendstream(no_data=True)

        with _populate_sendstream_dict(res.setdefault('mutate_ops', {})) as d:
            d['sendstream'] = _make_mutate_ops_subvolume(
                subvols, create_ops, os.path.join(temp_dir, b'mutate_ops'),
            ).get_sendstream(parent=create_ops)

        return res


@contextlib.contextmanager
def _root_owned_world_viewable_temp_dir(base_dir: bytes):  # yields bytes
    temp_dir, _ = subprocess.run([
        'sudo', 'mktemp', '-d', '-p', base_dir
    ], stdout=subprocess.PIPE, check=True).stdout.rsplit(b'\n', 1)
    try:
        subprocess.run(['sudo', 'chmod', 'og+rx', temp_dir], check=True)
        yield temp_dir
    except BaseException:  # Yes, even KeyboardInterrupt & SystemExit
        subprocess.run(['sudo', 'rmdir', temp_dir], check=True)
        raise


# Takes `path_in_repo` because this is part of the library interface, and
# thus must work in @mode/opt, and thus we cannot use `__file__` here.
def make_demo_sendstreams(path_in_repo):
    # We need `root` to create a directory in `buck-image-out/volume`, but
    # we also need it to be user-accessible so that we can use `cwd=` to
    # simplify our subprocess invocations.
    with _root_owned_world_viewable_temp_dir(get_volume_for_current_repo(
        1e8, ensure_per_repo_artifacts_dir_exists(path_in_repo),
    )) as temp_dir:
        return _make_demo_sendstreams(temp_dir)


def _main():
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
    args = p.parse_args()

    # __file__ won't let us find the repo in @mode/opt, but that's OK, since
    # this is only used as a binary for development purposes.
    sendstream_dict = make_demo_sendstreams(__file__)

    # This width makes the `--dump`ed commands fit on one line.
    prettified = pprint.pformat(sendstream_dict, width=200).encode()
    pickled = pickle.dumps(sendstream_dict)

    if args.print == Print.PRETTY:
        sys.stdout.buffer.write(prettified)
    elif args.print == Print.PICKLE:
        sys.stdout.buffer.write(pickled)
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


def gold_demo_sendstreams():
    with open(
        os.path.join(
            # We are part of the library interface, but __file__ works because:
            #   (a) we never use par_style = "fastzip", and
            #   (b) the gold data is baked into the PAR for reading.
            os.path.dirname(os.path.abspath(__file__)),
            'gold_demo_sendstreams.pickle',
        ),
        'rb',
    ) as f:
        return pickle.load(f)


if __name__ == '__main__':
    _main()
