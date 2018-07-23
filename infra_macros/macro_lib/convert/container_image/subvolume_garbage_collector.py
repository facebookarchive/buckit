#!/usr/bin/env python3
'''\
This pre-initializes a Buck-given "$OUT" (`--new-subvolume-json`) with a
hardlink that serves as a refcount to distinguish subvolumes that are
referenced by the Buck cache ("live") from ones that are not ("dead").

We hardlink the "subvolume JSON" outputs from Buck's output directory into a
directory we own.  Given these hardlinks, we can garbage-collect any
subvolumes, which do **not** have a hardlink at all, or whose link count
drops to 1.  This works because in building the output, Buck actually `mv`s
the new output on top of the old one, which unlinks the previous version --
but we also try to `unlink "$OUT"`, just in case.

KEY ASSUMPTIONS:

 - `buck-out/` (containing `--new-subvolume-json`) is on the same filesystem
    as `--refcounts-dir` (which lives in the the source repo).

 - Two garbage collector instances NEVER run concurrently with the same
   (`--new-subvolume-name`, `--new-subvolume-version`) NOR with the same
   `--new-subvolume-json`.  In practice, the former is assured because
   `subvolume_version.py` returns a unique number for each new build.  The
   latter is (hopefully) guaranteed by Buck -- presumably, it does not
   concurrently start two builds with the same output.  Protecting against
   this with something like `flock` is too onerous (lockfiles can never be
   deleted), so we just assume our caller is sane.
'''
import argparse
import fcntl
import glob
import logging
import os
import re
import stat
import subprocess
import sys

log = logging.Logger(__name__)


def list_subvolumes(subvolumes_dir):
    # Ignore subvolumes that don't match the pattern.
    subvolumes = [
        os.path.relpath(p, subvolumes_dir)
            for p in glob.glob(f'{subvolumes_dir}/*:*/')
    ]
    # If glob works correctly, this list should always be empty.
    bad_subvolumes = [s for s in subvolumes if '/' in s]
    assert not bad_subvolumes, f'{bad_subvolumes} globbing {subvolumes_dir}'
    return subvolumes


def list_refcounts(refcounts_dir):
    reg = re.compile('^(.+):([^:]+).json$')
    for p in glob.glob(f'{refcounts_dir}/*:*.json'):
        m = reg.match(os.path.basename(p))
        # Only fails if glob does not work.
        assert m is not None, f'Bad refcount item {p} in {refcounts_dir}'
        st = os.stat(p)
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f'Refcount {p} is not a regular file')
        # It is tempting to check that the subvolume name & version match
        # `SubvolumeOnDisk.from_json_file`, but we cannot do that because
        # our GC pass might be running concurrently with another build, and
        # the refcount file might be empty or half-written.
        yield (f'{m.group(1)}:{m.group(2)}', st.st_nlink)


def garbage_collect_subvolumes(refcounts_dir, subvolumes_dir):
    # IMPORTANT: We must list subvolumes BEFORE refcounts. The risk is that
    # this runs concurrently with another build, which will create a new
    # refcount & subvolume (in that order).  If we read refcounts first, we
    # might end up winning the race against the other build, and NOT reading
    # the new refcount.  If we then lose the second part of the race, we
    # would find the subvolume that the other process just created, and
    # delete it.
    subvols = set(list_subvolumes(subvolumes_dir))
    subvol_to_nlink = dict(list_refcounts(refcounts_dir))

    # Delete subvolumes with insufficient refcounts.
    for subvol in subvols:
        nlink = subvol_to_nlink.get(subvol, 0)
        if nlink >= 2:
            if nlink > 2:
                # Not sure how this might happen, but it seems non-fatal...
                log.error(f'{nlink} > 2 links to subvolume {subvol}')
            continue
        refcount_path = os.path.join(refcounts_dir, f'{subvol}.json')
        log.warning(
            f'Deleting {subvol} and its refcount {refcount_path}, since the '
            f'refcount has {nlink} links'
        )
        # Unlink the refcount first to slightly decrease the chance of
        # leaving an orphaned refcount file on disk.  Most orphans will come
        # from us failing to get to the point where we create a subvolume.
        if nlink:
            os.unlink(refcount_path)
        subprocess.check_call([
            'sudo', 'btrfs', 'subvolume', 'delete',
            os.path.join(subvolumes_dir, subvol)
        ])

    # Unfortunately, I see no safe way to delete refcounts that lack
    # subvolumes, although here would be the right place to do it.  The
    # reason is that we cannot create the refcount and the subvolume
    # "atomically" (i.e. under `flock`) due to the way the current aimage
    # builder works.  So for now, let's just leak the orphan refcounts
    # -- they shouldn't happen anyway unless a build breaks in the narrow
    # window between refcount creation & subvolume creation.


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        '--refcounts-dir', required=True,
        help='We will create a hardlink to `--new-subvolume-json` in this '
            'directory. For that reason, this needs to be on same device, '
            'and thus cannot be under `--subvolumes-dir`',
    )
    parser.add_argument(
        '--subvolumes-dir', required=True,
        help='A directory on a btrfs volume'
    )
    parser.add_argument(
        '--new-subvolume-name',
        help='The first part of the subvolume directory name',
    )
    parser.add_argument(
        '--new-subvolume-version',
        help='The second part of the subvolume directory name',
    )
    parser.add_argument(
        '--new-subvolume-json',
        help='We will delete any file at this path, then create an empty one, '
            'and hard-link into `--refcounts-dir` for refcounting purposes. '
            'The image compiler will then write data into this file.',
    )
    return parser.parse_args(argv)


def has_new_subvolume(args):
    new_subvolume_args = (
        args.new_subvolume_name,
        args.new_subvolume_version,
        args.new_subvolume_json,
    )
    if None not in new_subvolume_args:
        return True
    if new_subvolume_args != (None,) * 3:
        raise RuntimeError(
            'Either pass all 3 --new-subvolume-* arguments, or pass none.'
        )
    return False


def subvolume_garbage_collector(argv):
    '''
    IMPORTANT:

     - Multiple copies of this function can run concurrently, subject to the
       MAIN ASSUMPTIONS in the file's docblock.

     - The garbage-collection pass must be robust against failures in the
       middle of the code (imagine somebody hitting Ctrl-C, or worse).

       Here is why this code resists interruptions. It makes these writes:
         (a) unlinks the subvolume json & refcount for the new subvolume
             being created,
         (b) deletes subvolumes with insufficient refcounts,
         (c) populates an empty subvolume json + linked refcount.

       Failing during or after (a) is fine -- it'll have the side effect of
       making the subvolume eligible to be GC'd by another build, but as far
       as I know, Buck will consider the subvolume's old json output dead
       anyhow.  (The fix is easy if it turns out to be a problem.)

       Failing during (b) is also fine. Presumably, `btrfs subvolume delete`
       is atomic, so at worst we will not delete ALL the garbage.

       Failure before (c), or in the middle of (c) will abort the build, so
       the lack of a refcount link won't cause issues later.
    '''
    args = parse_args(argv)

    # Delete unused subvolumes.
    #
    # The below `flock` mutex prevents more than one of these GC passes from
    # running concurrently.  The docs of `garbage_collect_subvolumes`
    # explain why a GC pass can safely concurrently run with a build.
    #
    # We don't set CLOEXEC on this FD because we actually want `sudo btrfs`
    # to inherit it and hold the lock while it does its thing.  It seems OK
    # to trust that `btrfs` will not be doing shenanigans like daemonizing a
    # service that runs behind our back.
    fd = os.open(args.subvolumes_dir, os.O_RDONLY)
    try:
        # Don't block here to avoid serializing the garbage-collection
        # passes of concurrently running builds.  This may increase disk
        # usage, but overall, the build speed should be better.  Caveat: I
        # don't have meaningful benchmarks to substantiate this, so this is
        # just informed demagoguery ;)
        #
        # Future: if disk usage is a problem, we can loop this code until no
        # deletions are made.  For bonus points, daemonize the loop so that
        # the build that triggered the GC actually gets to make progress.
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            garbage_collect_subvolumes(args.refcounts_dir, args.subvolumes_dir)
        except BlockingIOError:
            # They probably won't clean up the prior version of the
            # subvolume we are creating, but we don't rely on that to make
            # space anyhow, so let's continue.
            log.warning('A concurrent build is garbage-collecting subvolumes.')
            pass
    finally:
        os.close(fd)  # Don't hold the lock any longer than we have to!

    # .json outputs and refcounts are written as an unprivileged user. We
    # only need root for subvolume manipulation (above).
    try:
        os.mkdir(args.refcounts_dir)
    except FileExistsError:  # Don't fail on races to `mkdir`.
        pass

    # Prepare the output file for the compiler to write into. We'll need the
    # json output to exist to hardlink it.  But, first, ensure it does not
    # exist so that its link count starts at 1.  Finally, make the hardlink
    # that will serve as a refcount for `garbage_collect_subvolumes`.
    #
    # The `unlink` & `open` below are concurrency-safe per one of MAIN
    # ASSUMPTIONS above.  Specifically, Buck's should not ever run 2 build
    # processes with the same output file.
    #
    # The hardlink won't interact with concurrent GC passes, either.
    #  1) Since the subvolume ID is unique, no other process will race to
    #     create the hardlink.
    #  2) Another GC will never delete our subvolume, because we create
    #     subvolumes **after** creating refcounts, while
    #     `garbage_collect_subvolumes` enumerates subvolumes **before**
    #     reading refcounts.
    if has_new_subvolume(args):
        new_subvolume_refcount = os.path.join(
            args.refcounts_dir,
            f'{args.new_subvolume_name}:{args.new_subvolume_version}.json',
        )
        # This should never happen since the name & version are supposed to
        # be unique for this one subvolume (MAIN ASSUMPTIONS).
        if os.path.exists(new_subvolume_refcount):
            raise RuntimeError(
                f'Refcount already exists: {new_subvolume_refcount}'
            )

        # Our refcounting relies on the hard-link counts of the output
        # files.  Therefore, we must not write into an existing output file,
        # and must instead unlink and re-create it.  NB: At present, Buck
        # actually gives us an empty directory, so this is done solely for
        # robustness.
        for p in (new_subvolume_refcount, args.new_subvolume_json):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
        open(args.new_subvolume_json, 'a').close()

        # Throws if the Buck output is not on the same device as the
        # refcount dir.  That case has to fail, that's how hardlinks work.
        # However, it's easy enough to make the refcounts dir a symlink to a
        # directory on the appropriate device, so this is a non-issue.
        os.link(args.new_subvolume_json, new_subvolume_refcount)


if __name__ == '__main__':
    subvolume_garbage_collector(sys.argv[1:])  # pragma: no cover
