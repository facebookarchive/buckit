#!/usr/bin/env python3
import os
import subprocess
import sys
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
        ret = self._nspawn_in(
            'host', ['--', 'sh', '-c', 'echo ohai ; echo abracadabra >&2'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # The extra newline is due to T40936918 mentioned in
        # `nspawn_in_subvol.py`.  It would disappear if I passed `--quiet`
        # to nspawn, but I want to retain the extra debug logging.
        self.assertEqual(b'ohai\n\n', ret.stdout)
        # stderr is not just a clean `abracadabra\n` because we don't
        # suppress nspawn's debugging output.
        self.assertIn(b'abracadabra\n', ret.stderr)

    def test_machine_id(self):
        # Whether or not the layer filesystem had a machine ID, it should
        # not be visible in the container.
        for resource in ('host', 'host-with-machine-id', 'host-no-machine-id'):
            self._nspawn_in(resource, [
                '--', 'sh', '-uexc',
                # Either the file does not exist, or it is empty.
                'test \\! -s /etc/machine-id && test -z "$container_uuid"',
            ])

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
            'sh', '-c', 'echo ohaibai > /poke',
        ])
        with open(dest_subvol.path('poke')) as f:
            self.assertEqual('ohaibai\n', f.read())
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
