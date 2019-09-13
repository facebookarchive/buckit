#!/usr/bin/env python3
import os
import subprocess

from typing import List

from fs_image.common import nullcontext
from subvol_utils import Subvol

from compiler.provides import ProvidesDirectory, ProvidesFile
from compiler.requires import require_directory

from .common import (
    coerce_path_field_normal_relative, ImageItem, LayerOpts,
    make_path_normal_relative,
)


def _maybe_popen_zstd(path):
    'Use this as a context manager.'
    if path.endswith(b'.zst'):
        return subprocess.Popen([
            'zstd', '--decompress', '--stdout', path,
        ], stdout=subprocess.PIPE)
    return nullcontext()


def _open_tarfile(path):
    'Wraps tarfile.open to add .zst support. Use this as a context manager.'
    import tarfile  # Lazy since only this method needs it.
    with _maybe_popen_zstd(path) as maybe_proc:
        if maybe_proc is None:
            return tarfile.open(path)
        else:
            return tarfile.open(fileobj=maybe_proc.stdout, mode='r|')


class TarballItem(metaclass=ImageItem):
    fields = ['into_dir', 'source', 'force_root_ownership']

    def customize_fields(kwargs):  # noqa: B902
        coerce_path_field_normal_relative(kwargs, 'into_dir')
        assert kwargs['force_root_ownership'] in [True, False], kwargs

    def provides(self):
        with _open_tarfile(self.source) as f:
            for item in f:
                path = os.path.join(
                    self.into_dir, make_path_normal_relative(item.name),
                )
                if item.isdir():
                    # We do NOT provide the installation directory, and the
                    # image build script tarball extractor takes pains (e.g.
                    # `tar --no-overwrite-dir`) not to touch the extraction
                    # directory.
                    if os.path.normpath(
                        os.path.relpath(path, self.into_dir)
                    ) != '.':
                        yield ProvidesDirectory(path=path)
                else:
                    yield ProvidesFile(path=path)

    def requires(self):
        yield require_directory(self.into_dir)

    def build(self, subvol: Subvol, layer_opts: LayerOpts):
        with _maybe_popen_zstd(self.source) as maybe_proc:
            subvol.run_as_root([
                'tar',
                # Future: Bug: `tar` unfortunately FOLLOWS existing symlinks
                # when unpacking.  This isn't dire because the compiler's
                # conflict prevention SHOULD prevent us from going out of
                # the subvolume since this TarballItem's provides would
                # collide with whatever is already present.  However, it's
                # hard to state that with complete confidence, especially if
                # we start adding support for following directory symlinks.
                '-C', subvol.path(self.into_dir),
                '-x',
                # Block tar's weird handling of paths containing colons.
                '--force-local',
                # The uid:gid doing the extraction is root:root, so by default
                # tar would try to restore the file ownership from the archive.
                # In some cases, we just want all the files to be root-owned.
                *(['--no-same-owner'] if self.force_root_ownership else []),
                # The next option is an extra safeguard that is redundant
                # with the compiler's prevention of `provides` conflicts.
                # It has two consequences:
                #
                #  (1) If a file already exists, `tar` will fail with an error.
                #      It is **not** an error if a directory already exists --
                #      otherwise, one would never be able to safely untar
                #      something into e.g. `/usr/local/bin`.
                #
                #  (2) Less obviously, the option prevents `tar` from
                #      overwriting the permissions of `directory`, as it
                #      otherwise would.
                #
                #      Thanks to the compiler's conflict detection, this should
                #      not come up, but now you know.  Observe us clobber the
                #      permissions without it:
                #
                #        $ mkdir IN OUT
                #        $ touch IN/file
                #        $ chmod og-rwx IN
                #        $ ls -ld IN OUT
                #        drwx------. 2 lesha users 17 Sep 11 21:50 IN
                #        drwxr-xr-x. 2 lesha users  6 Sep 11 21:50 OUT
                #        $ tar -C IN -czf file.tgz .
                #        $ tar -C OUT -xvf file.tgz
                #        ./
                #        ./file
                #        $ ls -ld IN OUT
                #        drwx------. 2 lesha users 17 Sep 11 21:50 IN
                #        drwx------. 2 lesha users 17 Sep 11 21:50 OUT
                #
                #      Adding `--keep-old-files` preserves `OUT`'s metadata:
                #
                #        $ rm -rf OUT ; mkdir out ; ls -ld OUT
                #        drwxr-xr-x. 2 lesha users 6 Sep 11 21:53 OUT
                #        $ tar -C OUT --keep-old-files -xvf file.tgz
                #        ./
                #        ./file
                #        $ ls -ld IN OUT
                #        drwx------. 2 lesha users 17 Sep 11 21:50 IN
                #        drwxr-xr-x. 2 lesha users 17 Sep 11 21:54 OUT
                '--keep-old-files',
                '-f', ('-' if maybe_proc else self.source),
            ], stdin=(maybe_proc.stdout if maybe_proc else None))
