#!/usr/bin/env python3
'''
This test runs Buck-built binaries that were installed into an image.

Note that the implementation of executables in @mode/dev is quite
dramatically different from that in @mode/opt, so remember to run both while
developing to avoid later surprises from CI.
'''
import os
import subprocess
import unittest

from nspawn_in_subvol import find_built_subvol, nspawn_in_subvol, parse_opts


class ExecuteInstalledTestCase(unittest.TestCase):

    def _nspawn_in(self, rsrc_name, args, **kwargs):
        opts = parse_opts([
            '--quiet',  # Easier to assert the output.
            # __file__ works in @mode/opt since the resource is inside the XAR
            '--layer', os.path.join(os.path.dirname(__file__), rsrc_name),
        ] + args)
        return nspawn_in_subvol(find_built_subvol(opts.layer), opts, **kwargs)

    def test_execute(self):
        for print_ok in [
            '/foo/bar/installed/print-ok',
            '/foo/bar/installed/print-ok-too',
        ]:
            ret = self._nspawn_in(
                'exe-layer', [print_ok],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual((b'ok\n', b''), (ret.stdout, ret.stderr))
