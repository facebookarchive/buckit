#!/usr/bin/env python3
'''
When developing images, it is very handy to be able to run code inside an
image.  This target lets you do just that, for example, here is a shell:

    buck run //fs_image:nspawn-run-in-subvol -- --layer "$(
        buck build --show-output \\
            //fs_image/compiler/tests:only-for-tests-read-only-host-clone |
                cut -f 2- -d ' '
    )" -- /bin/bash

The above is a handful to remember, so each layer gets a corresponding
`-container` target.  To be used like so:

    buck run //PATH/TO:SOME_LAYER-container  # Runs `bash` by default
    buck run //PATH/TO:SOME_LAYER-container -- -- printenv

Note that there are two sets of `--`.  The first separates `buck run`
arguments from those of the container runtime.  The second separates the
container args from the in-container command.

IMPORTANT: This is NOT READY to use as a sandbox for build steps.  The
reason is that `systemd-nspawn` does a bunch of random things to the
filesystem, which we would need to explicitly control (see "Filesystem
mutations" below).


## Known issues

  - The `hostname` of the container is not currently set to a useful value,
    which can affect some network operations.

  - T40937041: If `stdout` is a PTY, then `stderr` redirection does not work
    -- the container's `stderr` will also point at the PTY.  This is an
    nspawn bug, and working around it form this wrapper would be hard.

  - T40936918: At present, `nspawn` prints a spurious newline to stdout,
    even if `stdout` is redirected.  This is due to an errant `putc('\\n',
    stdout);` in `nspawn.c`.  This will most likely be fixed in future
    releases of systemd.  I could work around this in the wrapper by passing
    `--quiet` when `not sys.stdout.isatty()`.  However, that loses valuable
    debugging output, so I'm not doing it yet.


## What does nspawn do, roughly?

This section is as of systemd 238/239, and will never be 100% perfect.  For
production-readiness, we would want to write automatic tests of nspawn's
behavior (especially, against minimal containers) to ensure future `systemd`
releases don't surprise us by creating yet-more filesystem objects.


### Isolates all specified kernel namespaces

  - pid
  - mount
  - network with --private-network
  - uts & ipc
  - cgroup (if supported by the base system)
  - user (if requested, we don't request it below due to kernel support)


### Filesystem mutations and requirements

`nspawn` will refuse to use a directory unless these two exist:
  - `/usr/`
  - an `os-release` file

`nspawn` will always ensure these exist before starting its container:
  - /dev
  - /etc
  - /lib will symlink to /usr/lib if the latter exists, but the former does not
  - /proc
  - /root -- permissions nonstandard, should be 0700 not 0755.
  - /run
  - /sys
  - /tmp
  - /var/log/journal/

`nspawn` wants to modify `/etc/resolv.conf` if `--private-network` is off.

The permissions of the created directories seem to be 0755 by default, and
all are owned by root (except for $HOME which may depend if we vary the
user, which we should probably never do).


## Future

  - Support for `--boot`?  For now, we just run a single process in the
    foreground, but --boot may be required if a Chef cookbook needs to talk
    to the resident systemd.

  - Should we drop CAP_NET_ADMIN, or any other capabilities?  Note that
    NET_ADMIN might be needed to set up `--private-network` interfaces.

  - Can we get any mileage out of --system-call-filter?

'''
import argparse
import os
import pwd
import re
import subprocess
import sys
import uuid

from contextlib import contextmanager

from artifacts_dir import find_repo_root
from common import nullcontext
from compiler.mount_item import clone_mounts
from find_built_subvol import find_built_subvol, Subvol
from send_fds_and_run import popen_and_inject_fds_after_sudo
from tests.temp_subvolumes import TempSubvolumes


def _colon_quote_path(path):
    return re.sub('[\\\\:]', lambda m: '\\' + m.group(0), path)


# NB: This assumes the path is readable to unprivileged users.
def _exists_in_image(subvol, path):
    return os.path.exists(subvol.path(path))


def bind_args(src, dest=None, *, readonly=True):
    'dest is relative to the nspawn container root'
    if dest is None:
        dest = src
    # NB: The `systemd-nspawn` docs claim that we can add `:norbind` to make
    # the bind mount non-recursive.  This would be a bad default, so we
    # don't do it, but if you wanted to add it a non-recursive option, be
    # sure to test that nspawn actually implements the functionality -- it's
    # not very obvious from the code that it does (as of 8f6b442a7).
    return [
        '--bind-ro' if readonly else '--bind',
        f'{_colon_quote_path(src)}:{_colon_quote_path(dest)}',
    ]


def _obfuscate_machine_id_args(nspawn_subvol):
    '''
    Ensure that the machine ID is not known inside the container.

    This is important because images are usually built to be executed on an
    indeterminate future machine, not on a specific known machine.  Building
    with a fixed machine ID could potentially result in that ID leaking into
    the image content (via hashes or directly), and creating issues at
    runtime, when that machine ID would necessarily change.

    The mechanism is as follows.  First, we never pass `--uuid`.  Second, we
    ensure that the container either lacks `/etc/machine-id`, or that this
    file is empty.  In neither case does `nspawn` write the machine ID into
    `/etc/machine-id`.  Instead, it sets the environment variable
    `container_uuid` to the `machine-id` that our bind-mount has shadowed,
    or to a random value if none was set.  We avoid this UUID leak by asking
    `nspawn` to make `container_uuid` empty.
    '''
    hide_id_args = ['--setenv=container_uuid=']
    if _exists_in_image(nspawn_subvol, '/etc/machine-id'):
        # Shadow a pre-existing `machine-id` with an empty file.
        return hide_id_args + bind_args('/dev/null', '/etc/machine-id')
    return hide_id_args


def _inject_os_release_args(subvol):
    '''
    nspawn requires os-release to be present as a "sanity check", but does
    not use it.  We do not want to block running commands on the image
    before it is created, so make a fake.
    '''
    os_release_paths = ['/usr/lib/os-release', '/etc/os-release']
    for path in os_release_paths:
        if _exists_in_image(subvol, path):
            return []
    # Not covering this with tests because it requires setting up a new test
    # image just for this case.  If we supported nested bind mounts, that
    # would be easy, but we do not.
    return bind_args('/dev/null', os_release_paths[0])  # pragma: no cover


def nspawn_cmd(nspawn_subvol):
    return [
        # Without this, nspawn would look for the host systemd's cgroup setup,
        # which breaks us in continuous integration containers, which may not
        # have a `systemd` in the host container.
        #
        # We set this variable via `env` instead of relying on the `sudo`
        # configuration because it's important that it be set.
        'env', 'UNIFIED_CGROUP_HIERARCHY=yes',
        'systemd-nspawn',
        # These are needed since we do not want to require a working `dbus` on
        # the host.
        '--register=no', '--keep-unit',
        # Some of the commands we will run will not work correctly as PID 1.
        '--as-pid2',
        # Randomize --machine so that the container has a random hostname
        # each time. The goal is to help detect builds that somehow use the
        # hostname to influence the resulting image.
        '--machine', uuid.uuid4().hex,
        '--directory', nspawn_subvol.path(),
        *_obfuscate_machine_id_args(nspawn_subvol),
        *_inject_os_release_args(nspawn_subvol),
        # Don't pollute the host's /var/log/journal
        '--link-journal=no',
        # Explicitly do not look for any settings for our ephemeral machine
        # on the host.
        '--settings=no',
        # Prevents the container from re-acquiring e.g. the mknod capability.
        '--no-new-privileges=1',
        # The timezone should be set up explicitly, not by nspawn's fiat.
        '--timezone=off',  # requires v239+
    ]


def nspawn_sanitize_env():
    env = os.environ.copy()
    # `systemd-nspawn` responds to a bunch of semi-private and intentionally
    # (mostly) undocumented environment variables.  Many of these can
    # compromise namespacing / isolation, which we emphatically do not want,
    # so let's prevent the ambient environment from changing them!
    #
    # Of course, this leaves alone a lot of the canonical variables
    # LINES/COLUMNS, or locale controls.  Those should be OK.
    for var in list(env.keys()):
        # No test coverage for this because (a) systemd does not pass such
        # environment vars to the container, so the only way to observe them
        # being set (or not) is via indirect side effects, (b) all the side
        # effects are annoying to test.
        if var.startswith('SYSTEMD_NSPAWN_'):  # pragma: no cover
            env.pop(var)
    return env


@contextmanager
def _snapshot_subvol(src_subvol, snapshot_into):
    if snapshot_into:
        nspawn_subvol = Subvol(snapshot_into)
        nspawn_subvol.snapshot(src_subvol)
        clone_mounts(src_subvol, nspawn_subvol)
        yield nspawn_subvol
    else:
        with TempSubvolumes() as tmp_subvols:
            # To make it easier to debug where a temporary subvolume came
            # from, make make its name resemble that of its source.
            tmp_name = os.path.normpath(src_subvol.path())
            tmp_name = os.path.basename(os.path.dirname(tmp_name)) or \
                os.path.basename(tmp_name)
            nspawn_subvol = tmp_subvols.snapshot(src_subvol, tmp_name)
            clone_mounts(src_subvol, nspawn_subvol)
            yield nspawn_subvol


def nspawn_in_subvol(
    src_subvol, opts, *,
    # These keyword-only arguments generally follow those of `subprocess.run`.
    #   - `check` defaults to True instead of False.
    #   - Unlike `run_as_root`, `stdout` is NOT default-redirected to `stderr`.
    stdout=None, stderr=None, check=True,
):
    extra_nspawn_args = ['--user', opts.user]

    if opts.private_network:
        extra_nspawn_args.append('--private-network')

    if opts.bind_repo_ro:
        # NB: Since this bind mount is only made within the nspawn
        # container, it is not visible in the `--snapshot-into` filesystem.
        # This is a worthwhile trade-off -- it is technically possible to
        # reimplement this kind of transient mount outside of the nspawn
        # container.  But, by making it available in the outer mount
        # namespace, its unmounting would become unreliable, and handling
        # that would add a bunch of complex code here.
        extra_nspawn_args.extend(bind_args(find_repo_root(sys.argv[0])))
        # Future: we **may** also need to mount the scratch directory
        # pointed to by `buck-image-out`, since otherwise repo code trying
        # to access other built layers won't work.  Not adding it now since
        # that seems like a rather esoteric requirement for the sorts of
        # code we should be running under `buck test` and `buck run`.  NB:
        # As of this writing, `scratch` works incorrectly under `nspawn`,
        # making `artifacts-dir` fail.

    if opts.logs_tmpfs:
        # Future: Don't assume that the image password DB is compatible
        # with the host's, and look there instead.
        pw = pwd.getpwnam(opts.user)
        extra_nspawn_args.extend(['--tmpfs', '/logs:' + ','.join([
            f'uid={pw.pw_uid}', f'gid={pw.pw_gid}', 'mode=0755', 'nodev',
            'nosuid', 'noexec',
        ])])

    # Future: This is definitely not the way to go for providing device
    # nodes, but we need `/dev/fuse` right now to run XARs.  Let's invent a
    # systematic story later.  This cannot be an `image.feature` because of
    # the way that `nspawn` sets up `/dev`.
    #
    # Don't require coverage in case any weird test hosts lack FUSE.
    if os.path.exists('/dev/fuse'):  # pragma: no cover
        extra_nspawn_args.extend(['--bind-ro', '/dev/fuse'])

    if opts.forward_tls_env:
        for k, v in os.environ.items():
            if k.startswith('THRIFT_TLS_'):
                extra_nspawn_args.append('--setenv={}={}'.format(k, v))

    with (
        _snapshot_subvol(src_subvol, opts.snapshot_into) if opts.snapshot
            else nullcontext(src_subvol)
    ) as nspawn_subvol:

        def popen(cmd):
            return nspawn_subvol.popen_as_root(
                cmd,
                # This is a safeguard in case `sudo` lets through these
                # unwanted environment variables.
                env=nspawn_sanitize_env(),
                # `run_as_root` sends stdout to stderr by default -- avoid that
                stdout=(1 if stdout is None else stdout),
                stderr=stderr,
                check=check,
            )

        cmd = [
            *nspawn_cmd(nspawn_subvol),
            *extra_nspawn_args,
            # Ensure that the command is not interpreted as nspawn args
            '--', *opts.cmd,
        ]
        with (
            # Avoid the overhead of the FD-forwarding wrapper if it's not needed
            popen_and_inject_fds_after_sudo(
                cmd, opts.forward_fd, popen, set_listen_fds=True,
            ) if opts.forward_fd else popen(cmd)
        ) as proc:
            stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(
            args=proc.args,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )


def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--layer', required=True,
        help='An `image.layer` output path (`buck targets --show-output`)',
    )
    parser.add_argument(
        '--snapshot', default=True, action='store_true',
        help='Make an snapshot of the layer before `nspawn`ing a container. '
             'By default, the snapshot is ephemeral, but you can also pass '
             '`--snapshot-into` to retain it (e.g. for debugging).',
    )
    parser.add_argument(
        '--no-snapshot', action='store_false', dest='snapshot',
        help='Run directly in the layer. Since layer filesystems are '
            'read-only, this only works if `nspawn` does not feel the '
            'need to modify the container filesystem. If it works for '
            'your layer today, it may still break in a future version '
            '`systemd` :/ ... but PLEASE do not even think about marking '
            'a layer subvolume read-write. That voids all warranties.',
    )
    parser.add_argument(
        '--snapshot-into', default='',
        help='Create a non-ephemeral snapshot of `--layer` at the specified '
            'non-existent path and prepare it to host an nspawn container. '
            'Defaults to empty, which makes the snapshot ephemeral.',
    )
    parser.add_argument(
        '--private-network', default=True, action='store_true',
        help='Pass `--private-network` to `systemd-nspawn`. This defaults '
            'to true to (a) encourage hermeticity, (b) because this stops '
            'nspawn from writing to resolv.conf in the image.',
    )
    parser.add_argument(
        '--no-private-network', action='store_false', dest='private_network',
        help='Do not pass `--private-network` to `systemd-nspawn`, letting '
            'container use the host network. You may also want to pass '
            '`--forward-tls-env`.',
    )
    parser.add_argument(
        '--forward-tls-env', action='store_true',
        help='Forwards into the container any environment variables whose '
            'names start with THRIFT_TLS_. Note that it is the responsibility '
            'of the layer to ensure that the contained paths are valid.',
    )
    parser.add_argument(
        '--bind-repo-ro', action='store_true',
        help='Makes a read-only recursive bind-mount of the current Buck '
             'project into the container at the same location as it is on '
             'the host. Needed to run in-place binaries.',
    )
    parser.add_argument(
        '--user', default='nobody',
        help='Changes to the specified user once in the nspawn container. '
            'Defaults to `nobody` to give you a mostly read-only view of '
            'the OS.',
    )
    parser.add_argument(
        '--no-logs-tmpfs', action='store_false', dest='logs_tmpfs',
        help='Our production runtime always provides a user-writable `/logs` '
            'in the container, so this wrapper simulates it by mounting a '
            'tmpfs at that location by default. You may need this flag to '
            'use `--no-snapshot` with an layer that lacks a `/logs` '
            'mountpoint. NB: we do not supply a persistent writable mount '
            'since that is guaranteed to break hermeticity and e.g. make '
            'somebody\'s image tests very hard to debug.',
    )
    parser.add_argument(
        '--forward-fd', type=int, action='append', default=[],
        help='These FDs will be copied into the container with sequential '
            'FD numbers starting from 3, in the order they were listed '
            'on the command-line. Repeat to pass multiple FDs.',
    )
    parser.add_argument(
        'cmd', nargs='*', default=['/bin/bash'],
        help='The command to run (as PID 2) in the container',
    )
    opts = parser.parse_args(argv)
    assert not opts.snapshot_into or opts.snapshot, opts
    return opts


# The manual test is in the first paragraph of the top docblock.
if __name__ == '__main__':  # pragma: no cover
    opts = parse_opts(sys.argv[1:])
    sys.exit(nspawn_in_subvol(
        find_built_subvol(opts.layer), opts, check=False,
    ).returncode)
