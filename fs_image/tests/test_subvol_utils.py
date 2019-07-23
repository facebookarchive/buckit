#!/usr/bin/env python3
import os
import subprocess
import tempfile
import unittest
import unittest.mock

from subvol_utils import Subvol, SubvolOpts, get_subvolume_path

from find_built_subvol import subvolumes_dir

from .temp_subvolumes import with_temp_subvols

class SubvolTestCase(unittest.TestCase):
    '''
    NB: The test here is partially redundant with demo_sendstreams, but
    coverage easier to manage when there's a clean, separate unit test.
    '''

    @with_temp_subvols
    def test_create_and_snapshot_and_already_exists(self, temp_subvols):
        p = temp_subvols.create('parent')
        p2 = Subvol(p.path(), already_exists=True)
        self.assertEqual(p.path(), p2.path())
        temp_subvols.snapshot(p2, 'child')

    def test_does_not_exist(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(AssertionError, 'No btrfs subvol'):
                Subvol(td, already_exists=True)

            sv = Subvol(td)
            with self.assertRaisesRegex(AssertionError, 'exists is False'):
                sv.run_as_root(['true'])

    def test_out_of_subvol_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            os.symlink('/dev/null', os.path.join(td, 'my_null'))
            self.assertEqual(
                os.path.join(td, 'my_null').encode(),
                Subvol(td).path('my_null', no_dereference_leaf=True),
            )
            with self.assertRaisesRegex(AssertionError, 'outside the subvol'):
                Subvol(td).path('my_null')

    def test_run_as_root_no_cwd(self):
        sv = Subvol('/dev/null/no-such-dir')
        sv.run_as_root(['true'], _subvol_exists=False)
        with self.assertRaisesRegex(AssertionError, 'cwd= is not permitte'):
            sv.run_as_root(['true'], _subvol_exists=False, cwd='.')

    def test_run_as_root_return(self):
        args = ['bash', '-c', 'echo -n my out; echo -n my err >&2']
        r = Subvol('/dev/null/no-such-dir').run_as_root(
            args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            _subvol_exists=False,
        )
        self.assertEqual(['sudo', 'TMP=', '--'] + args, r.args)
        self.assertEqual(0, r.returncode)
        self.assertEqual(b'my out', r.stdout)
        self.assertEqual(b'my err', r.stderr)

    def test_path(self):
        # We are only going to do path manipulations in this test.
        sv = Subvol('/subvol/need/not/exist')

        for bad_path in ['..', 'a/../../b/c/d', '../c/d/e']:
            with self.assertRaisesRegex(AssertionError, 'outside the subvol'):
                sv.path(bad_path)

        self.assertEqual(sv.path('a/b'), sv.path('/a/b/'))

        self.assertEqual(b'a/b', os.path.relpath(sv.path('a/b'), sv.path()))

        self.assertTrue(not sv.path('.').endswith(b'/.'))

    @with_temp_subvols
    def test_run_as_root_input(self, temp_subvols):
        sv = temp_subvols.create('subvol')
        sv.run_as_root(['tee', sv.path('hello')], input=b'world')
        with open(sv.path('hello')) as infile:
            self.assertEqual('world', infile.read())

    @with_temp_subvols
    def test_mark_readonly_and_get_sendstream(self, temp_subvols):
        sv = temp_subvols.create('subvol')
        sv.run_as_root(['touch', sv.path('abracadabra')])
        sendstream = sv.mark_readonly_and_get_sendstream()
        self.assertIn(b'abracadabra', sendstream)
        with tempfile.TemporaryFile() as outfile:
            with sv.mark_readonly_and_write_sendstream_to_file(outfile):
                pass
            outfile.seek(0)
            self.assertEqual(sendstream, outfile.read())

    @with_temp_subvols
    def test_mark_readonly_and_send_to_new_loopback(self, temp_subvols):
        sv = temp_subvols.create('subvol')
        sv.run_as_root([
            'dd', 'if=/dev/zero', b'of=' + sv.path('d'), 'bs=1M', 'count=200',
        ])
        sv.run_as_root(['mkdir', sv.path('0')])
        sv.run_as_root(['tee', sv.path('0/0')], input=b'0123456789')
        with tempfile.NamedTemporaryFile() as loop_path:
            # The default waste factor succeeds in 1 try, but a too-low
            # factor results in 2 tries.
            waste_too_low = 1.0001
            self.assertEqual(2, sv.mark_readonly_and_send_to_new_loopback(
                loop_path.name, waste_factor=waste_too_low,
            ))
            self.assertEqual(
                1, sv.mark_readonly_and_send_to_new_loopback(loop_path.name),
            )
            # Same 2-try run, but this time, exercise the free space check
            # instead of relying on parsing `btrfs receive` output.
            with unittest.mock.patch(
                'subvol_utils.Subvol._OUT_OF_SPACE_SUFFIX', b'cypa',
            ):
                self.assertEqual(2, sv.mark_readonly_and_send_to_new_loopback(
                    loop_path.name, waste_factor=waste_too_low,
                ))

    @with_temp_subvols
    def test_mark_readonly_and_send_to_new_loopback_writable(
        self,
        temp_subvols
    ):
        sv = temp_subvols.create('subvol')
        sv.run_as_root([
            'dd', 'if=/dev/zero', b'of=' + sv.path('d'), 'bs=1M', 'count=200',
        ])
        sv.run_as_root(['mkdir', sv.path('0')])
        sv.run_as_root(['tee', sv.path('0/0')], input=b'0123456789')
        with tempfile.NamedTemporaryFile() as loop_path:
            self.assertEqual(
                1, sv.mark_readonly_and_send_to_new_loopback(
                    loop_path.name, subvol_opts=SubvolOpts(readonly=False)),
            )

    def test_get_subvolume_path(self):
        layer_json = os.path.join(
            os.path.dirname(__file__), 'hello-layer', 'layer.json',
        )
        path = get_subvolume_path(layer_json, subvolumes_dir())
        self.assertTrue(os.path.exists(os.path.join(path, 'hello_world')))
