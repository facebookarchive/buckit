#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

from nspawn_in_subvol import (
    find_repo_root, find_built_subvol, nspawn_in_subvol, parse_opts,
)
from tests.temp_subvolumes import with_temp_subvols


class NspawnTestCase(unittest.TestCase):

    def _nspawn_in(self, rsrc_name, args, **kwargs):
        opts = parse_opts([
            # __file__ works in @mode/opt since the resource is inside the XAR
            '--layer', os.path.join(os.path.dirname(__file__), rsrc_name),
        ] + args)
        return nspawn_in_subvol(find_built_subvol(opts.layer), opts, **kwargs)

    def test_exit_code(self):
        self.assertEqual(37, self._nspawn_in(
            'host', ['--', 'sh', '-c', 'exit 37'], check=False,
        ).returncode)

    def test_redirects(self):
        cmd = ['--', 'sh', '-c', 'echo ohai && echo abracadabra >&2']
        ret = self._nspawn_in(
            'host', cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # The extra newline is due to T40936918 mentioned in
        # `nspawn_in_subvol.py`.  It would disappear if I passed `--quiet`
        # to nspawn, but I want to retain the extra debug logging.
        self.assertEqual(b'ohai\n\n', ret.stdout)
        # stderr is not just a clean `abracadabra\n` because we don't
        # suppress nspawn's debugging output.
        self.assertIn(b'abracadabra\n', ret.stderr)

        # The same test with `--quiet` is much simpler.
        ret = self._nspawn_in(
            'host', ['--quiet'] + cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(b'ohai\n', ret.stdout)
        self.assertEqual(b'abracadabra\n', ret.stderr)

    def test_machine_id(self):
        # Whether or not the layer filesystem had a machine ID, it should
        # not be visible in the container.
        for resource in ('host', 'host-with-machine-id', 'host-no-machine-id'):
            self._nspawn_in(resource, [
                '--', 'sh', '-uexc',
                # Either the file does not exist, or it is empty.
                'test \\! -s /etc/machine-id && test -z "$container_uuid"',
            ])

    def test_logs_directory(self):
        # The log directory is on by default.
        ret = self._nspawn_in('host', [
            '--', 'sh', '-c',
            'touch /logs/foo && stat --format="%U %G %a" /logs && whoami',
        ], stdout=subprocess.PIPE)
        self.assertEqual(0, ret.returncode)
        self.assertEqual(b'nobody nobody 755\nnobody\n\n', ret.stdout)
        # And the option prevents it from being created.
        self.assertEqual(0, self._nspawn_in('host', [
            '--no-logs-tmpfs', '--', 'test', '!', '-e', '/logs',
        ]).returncode)

    def test_forward_fd(self):
        with tempfile.TemporaryFile() as tf:
            tf.write(b'hello')
            tf.seek(0)
            ret = self._nspawn_in('host', [
                '--forward-fd', str(tf.fileno()), '--', 'sh', '-c',
                'cat <&3 && echo goodbye >&3',
            ], stdout=subprocess.PIPE)
            self.assertEqual(b'hello\n', ret.stdout)
            tf.seek(0)
            self.assertEqual(b'hellogoodbye\n', tf.read())

    @with_temp_subvols
    def test_non_ephemeral_snapshot(self, temp_subvols):
        dest_subvol = temp_subvols.caller_will_create('persistent')
        # We won't create this subvol by manipulating this very object, but
        # rather indirectly through its path.  So its _exists would never
        # get updated, which would cause the TempSubvolumes cleanup to fail.
        # Arguably, the cleanup should be robust to this, but since this is
        # the unique place we have to do it, keep it simple.
        dest_subvol._exists = True
        self._nspawn_in('host', [
            '--snapshot-into', dest_subvol.path().decode(), '--',
            # Also tests that we are a non-root user in the container.
            'sh', '-c', 'echo ohaibai "$USER" > /home/nobody/poke',
        ])
        with open(dest_subvol.path('/home/nobody/poke')) as f:
            self.assertEqual('ohaibai nobody\n', f.read())
        # Spot-check: the host mounts should still be available on the snapshot
        self.assertTrue(os.path.exists(dest_subvol.path('/bin/bash')))

    def test_bind_repo(self):
        self._nspawn_in('host', [
            '--bind-repo-ro', '--',
            'grep', 'supercalifragilisticexpialidocious',
            os.path.join(
                os.path.realpath(find_repo_root(sys.argv[0])),
                'fs_image/tests',
                os.path.basename(__file__),
            ),
        ])

    def test_cap_net_admin(self):
        self._nspawn_in('host', [
            '--user', 'root', '--no-private-network', '--cap-net-admin', '--',
            'unshare', '--net', 'ifconfig', 'lo', 'up',
        ])

    @unittest.mock.patch.dict('os.environ', {
        'THRIFT_TLS_KITTEH': 'meow', 'UNENCRYPTED_KITTEH': 'woof',
    })
    def test_tls_environment(self):
        ret = self._nspawn_in('host', [
            '--forward-tls-env', '--',
            'printenv', 'THRIFT_TLS_KITTEH', 'UNENCRYPTED_KITTEH',
        ], stdout=subprocess.PIPE, check=False)
        self.assertNotEqual(0, ret.returncode)  # UNENCRYPTED_KITTEH is unset
        self.assertEqual(b'meow\n\n', ret.stdout)

    def test_bindmount_rw(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as tmpdir2:
            self._nspawn_in('host', [
                '--user',
                'root',
                '--bindmount-rw',
                tmpdir, '/tmp',
                '--bindmount-rw',
                tmpdir2, '/mnt',
                '--',
                'touch',
                '/tmp/testfile',
                '/mnt/testfile',
            ])
            self.assertTrue(os.path.isfile(f'{tmpdir}/testfile'))
            self.assertTrue(os.path.isfile(f'{tmpdir2}/testfile'))

    def test_xar(self):
        'Make sure that XAR binaries work in vanilla `buck run` containers'
        ret = self._nspawn_in('host-hello-xar', [
            '--', '/hello.xar',
        ], stdout=subprocess.PIPE, check=True)
        self.assertEqual(b'hello world\n\n', ret.stdout)

    def test_mknod(self):
        'CAP_MKNOD is dropped by our runtime.'
        ret = self._nspawn_in('host', [
            '--user', 'root', '--quiet', '--', 'mknod', '/foo', 'c', '1', '3',
        ], stderr=subprocess.PIPE, check=False)
        self.assertNotEqual(0, ret.returncode)
        self.assertEqual(
            b"mknod: '/foo': Operation not permitted\n", ret.stderr,
        )
