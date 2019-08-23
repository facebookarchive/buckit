#!/usr/bin/env python3
import hashlib
import os
import subprocess
import tempfile

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
    if path.endswith('.zst'):
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


def _hash_tarball(tarball: str, algorithm: str) -> str:
    'Returns the hex digest'
    algo = hashlib.new(algorithm)
    with open(tarball, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            algo.update(chunk)
    return algo.hexdigest()


class TarballItem(metaclass=ImageItem):
    fields = ['into_dir', 'tarball', 'hash', 'force_root_ownership']

    def customize_fields(kwargs):  # noqa: B902
        algorithm, expected_hash = kwargs['hash'].split(':')
        actual_hash = _hash_tarball(kwargs['tarball'], algorithm)
        if actual_hash != expected_hash:
            raise AssertionError(
                f'{kwargs} failed hash validation, got {actual_hash}'
            )
        coerce_path_field_normal_relative(kwargs, 'into_dir')
        assert kwargs['force_root_ownership'] in [True, False], kwargs

    def provides(self):
        with _open_tarfile(self.tarball) as f:
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
        with _maybe_popen_zstd(self.tarball) as maybe_proc:
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
                '-f', ('-' if maybe_proc else self.tarball),
            ], stdin=(maybe_proc.stdout if maybe_proc else None))


def _generate_tarball(
    temp_dir: str, generator: bytes, generator_args: List[str],
) -> str:
    # API design notes:
    #
    #  1) The generator takes an output directory, not a file, because we
    #     prefer not to have to hardcode the extension of the output file in
    #     the TARGETS file -- that would make it more laborious to change
    #     the compression format.  Instead, the generator prints the path to
    #     the created tarball to stdout.  This does not introduce
    #     nondeterminism, since the tarball name cannot affect the result of
    #     its extraction.
    #
    #     Since TARGETS already hardcodes a content hash, requiring the name
    #     would not be far-fetched, this approach just seemed cleaner.
    #
    #  2) `temp_dir` is last since this allows the use of inline scripts via
    #     `generator_args` with e.g. `/bin/bash`.
    #
    # Future: it would be best to sandbox the generator to limit its
    # filesystem writes.  At the moment, we trust rule authors not to abuse
    # this feature and write stuff outside the given directory.
    tarball_filename = subprocess.check_output([
        generator, *generator_args, temp_dir,
    ]).decode()
    assert tarball_filename.endswith('\n'), (generator, tarball_filename)
    tarball_filename = os.path.normpath(tarball_filename[:-1])
    assert (
        not tarball_filename.startswith('/')
        and not tarball_filename.startswith('../')
    ), tarball_filename
    return os.path.join(temp_dir, tarball_filename)


def tarball_item_factory(
    exit_stack, *, generator: str = None, tarball: str = None,
    generator_args: List[str] = None, **kwargs,
):
    assert (generator is not None) ^ (tarball is not None)
    # Uses `generator` to generate a temporary `tarball` for `TarballItem`.
    # The file is deleted when the `exit_stack` context exits.
    #
    # NB: With `generator`, identical constructor arguments to this factory
    # will create different `TarballItem`s, so if we needed item
    # deduplication to work across inputs, this is broken.  However, I don't
    # believe the compiler relies on that.  If we need it, it should not be
    # too hard to share the same tarball for all generates with the same
    # command -- you'd add a global map of ('into_dir', 'command') ->
    # tarball, perhaps using weakref hooks to refcount tarballs and GC them.
    if generator:
        tarball = _generate_tarball(
            exit_stack.enter_context(tempfile.TemporaryDirectory()),
            generator,
            generator_args or [],
        )
    return TarballItem(**kwargs, tarball=tarball)
