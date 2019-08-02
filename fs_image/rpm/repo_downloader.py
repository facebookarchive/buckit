#!/usr/bin/env python3
'''
"Atomically" [1] downloads a snapshot of a single RPM repo.  Uses the
`repo_db.py` and `storage.py` abstractions to store the snapshot, while
avoiding duplication of RPMs that existed in prior snapshots.

Specifically, the user calls `RepoDownloader(...).download()`, which:

  - Downloads & parses `repomd.xml`.

  - Downloads the repodatas referenced there. Parses a primary repodata.

  - Downloads the RPMs referenced in the primary repodata.

Returns a `RepoSnapshot` containing descriptions to the stored objects.  The
dictionary keys are either "storage IDs" from the supplied `Storage` class,
or `ReportableError` instances for those that were not correctly downloaded
and stored.

[1] The snapshot is only atomic (i.e. representative of a single point in
time, as opposed to a sheared mix of the repo at various points in time) if:

  - Repodata files and RPM files are never mutated after creation. For
    repodata, this is plausible because their names include their hash.  For
    RPMs, this code includes a "mutable RPM" guard to detect files, whos
    contents changed.

  - `repomd.xml` is replaced atomically (i.e.  via `rename`) after making
    available all the new RPMs & repodatas.
'''
import hashlib
import requests
import urllib.parse

from contextlib import contextmanager
from io import BytesIO
from typing import Iterator, Iterable, List, Mapping, Optional, Set, Tuple

from fs_image.common import get_file_logger, nullcontext, set_new_key, shuffled

from .common import RpmShard
from .deleted_mutable_rpms import deleted_mutable_rpms
from .parse_repodata import get_rpm_parser, pick_primary_repodata
from .repo_objects import CANONICAL_HASH, Checksum, Repodata, RepoMetadata, Rpm
from .repo_db import RepoDBContext, RepodataTable, RpmTable
from .repo_snapshot import (
    FileIntegrityError, HTTPError, MutableRpmError, ReportableError,
    RepoSnapshot,
)
from .storage import Storage

# We'll download data in 512KB chunks. This needs to be reasonably large to
# avoid small-buffer overheads, but not too large, since we use `zlib` for
# incremental decompression in `parse_repodata.py`, and its API has a
# complexity bug that makes it slow for large INPUT_CHUNK/OUTPUT_CHUNK.
BUFFER_BYTES = 2 ** 19
log = get_file_logger(__file__)


class RepodataParseError(Exception):
    pass


@contextmanager
def _open_url(url: str) -> Iterable[BytesIO]:
    parsed_url = requests.utils.urlparse(url)
    if parsed_url.scheme == 'file':
        assert parsed_url.netloc == '', f'Bad file URL: {url}'
        with open(parsed_url.path, 'rb') as infile:
            yield infile
    elif parsed_url.scheme in ['http', 'https']:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            yield r.raw  # A file-like `io`-style object for the HTTP stream
    else:  # pragma: no cover
        raise RuntimeError(f'Unknown URL scheme in {url}')


def _read_chunks(input: BytesIO) -> Iterator[bytes]:
    while True:
        chunk = input.read(BUFFER_BYTES)
        if not chunk:
            break
        yield chunk


def _verify_chunk_stream(
    chunks: Iterable[bytes], checksums: Iterable[Checksum], size: int,
    location: str,
):
    actual_size = 0
    hashers = [ck.hasher() for ck in checksums]
    for chunk in chunks:
        actual_size += len(chunk)
        for hasher in hashers:
            hasher.update(chunk)
        yield chunk
    if actual_size != size:
        raise FileIntegrityError(
            location=location,
            failed_check='size',
            expected=size,
            actual=actual_size,
        )
    for hash, ck in zip(hashers, checksums):
        if hash.hexdigest() != ck.hexdigest:
            raise FileIntegrityError(
                location=location,
                failed_check=ck.algorithm,
                expected=ck.hexdigest,
                actual=hash.hexdigest(),
            )


def _log_if_storage_ids_differ(obj, storage_id, db_storage_id):
    if db_storage_id != storage_id:
        log.warning(
            f'Another writer already committed {obj} at {db_storage_id}, '
            f'will delete our copy at {storage_id}'
        )


@contextmanager
def _reportable_http_errors(location):
    try:
        yield
    except requests.exceptions.HTTPError as ex:
        # E.g. we can see 404 errors if packages were deleted
        # without updating the repodata.
        #
        # Future: If we see lots of transient error status codes
        # in practice, we could retry automatically before
        # waiting for the next snapshot, but the complexity is
        # not worth it for now.
        raise HTTPError(
            location=location,
            http_status=ex.response.status_code,
        )


class RepoDownloader:
    def __init__(
        self,
        repo_name: str,
        repo_url: str,  # Remember to URL-quote e.g. file:// paths here
        repo_db_ctx: RepoDBContext,
        storage: Storage,
    ):
        self._repo_name = repo_name
        self._repodata_table = RepodataTable()
        self._rpm_table = RpmTable()
        if not repo_url.endswith('/'):
            repo_url += '/'  # `urljoin` needs a trailing / to work right
        self._repo_url = repo_url
        self._repo_db_ctx = repo_db_ctx
        self._storage = storage

    @contextmanager
    def _download(self, relative_url):
        assert not relative_url.startswith('/')
        with _open_url(
            urllib.parse.urljoin(self._repo_url, relative_url)
        ) as input:
            yield input

    # May raise `ReportableError`s to be caught by `_download_repodatas`
    def _download_repodata(
        self, repodata: 'Repodata', *, is_primary: bool
    ) -> Tuple[bool, str, Optional[List[Rpm]]]:
        '''
          - Returns True only if we just downloaded & stored this Repodata.
          - Returns our new storage_id, or the previous one from the DB.
          - For the selected primary repodata, returns a list of RPMs.
            Returns None for all others.
        '''
        # We only need to download the repodata if is not already in the DB,
        # or if it is primary (so we can parse it for RPMs).
        with self._repo_db_ctx as repo_db:
            storage_id = repo_db.get_storage_id(self._repodata_table, repodata)
        if is_primary:
            rpms = []
        elif storage_id:
            return False, storage_id, None  # Nothing stored, not primary
        else:
            rpms = None

        with (
            # We will parse the selected primary file to discover the RPMs.
            get_rpm_parser(repodata) if is_primary else nullcontext()
        ) as rpm_parser, (
            # Read the primary from storage if we already have an ID --
            # downloading is more likely to fail due to repo updates.
            self._storage.reader(storage_id) if storage_id
                else self._download(repodata.location)
        ) as input, (
            # Only write to storage if it's not already there.
            self._storage.writer() if not storage_id else nullcontext()
        ) as output:
            log.info(f'Fetching {repodata}')
            for chunk in _verify_chunk_stream(
                _read_chunks(input),
                [repodata.checksum],
                repodata.size,
                repodata.location,
            ):  # May raise a ReportableError
                if output:
                    output.write(chunk)
                if rpm_parser:
                    try:
                        rpms.extend(rpm_parser.feed(chunk))
                    except Exception as ex:
                        raise RepodataParseError((repodata.location, ex))
            # Must commit from inside the output context to get a storage_id.
            if output:
                return True, output.commit(), rpms
        # The repodata was already stored, and we parsed it for RPMs.
        assert storage_id is not None
        return False, storage_id, rpms

    def _download_repodatas(
        self,
        repomd: RepoMetadata,
        # We mutate this dictionary on-commit to allow the caller to clean
        # up any stored repodata blobs if the download fails part-way.
        persist_storage_id_to_repodata: Mapping[str, Repodata],
        visitors: Iterable['RepoObjectVisitor'],
    ) -> Tuple[Set[Rpm], Mapping[str, Repodata]]:
        rpms = None  # We'll extract these from the primary repodata
        storage_id_to_repodata = {}  # Newly stored **and** pre-existing
        primary_repodata = pick_primary_repodata(repomd.repodatas)
        log.info(f'''`{self._repo_name}` repodata weighs {
            sum(rd.size for rd in repomd.repodatas)
        :,} bytes''')
        # Visitors see all declared repodata, even if some downloads fail.
        for visitor in visitors:
            for repodata in repomd.repodatas:
                visitor.visit_repodata(repodata)
        # Download in random order to reduce collisions from racing writers.
        for repodata in shuffled(repomd.repodatas):
            try:
                with _reportable_http_errors(repodata.location):
                    newly_stored, storage_id, maybe_rpms = \
                        self._download_repodata(
                            repodata, is_primary=repodata is primary_repodata,
                        )
                if newly_stored:
                    set_new_key(
                        persist_storage_id_to_repodata, storage_id, repodata,
                    )
                if maybe_rpms is not None:
                    # Convert to a set to work around buggy repodatas, which
                    # list the same RPM object twice.
                    rpms = set(maybe_rpms)
            except ReportableError as ex:
                # We cannot proceed without the primary file -- raise here
                # to trigger the "top-level retry" in the snapshot driver.
                if repodata is primary_repodata:
                    raise
                # This fake "storage ID" is not written to
                # `persist_storage_id_to_repodata`, so we will never attempt
                # to write it to the DB.  However, it does end up in
                # `repodata.json`, so the error is visible.
                storage_id = ex
            set_new_key(storage_id_to_repodata, storage_id, repodata)

        assert len(storage_id_to_repodata) == len(repomd.repodatas)
        assert rpms, 'Is the repo empty?'
        return rpms, storage_id_to_repodata

    # May raise `ReportableError`s to be caught by `_download_rpms`.
    # May raise a `requests.HTTPError` if the download fails.
    def _download_rpm(self, rpm: Rpm) -> Tuple[str, Rpm]:
        'Returns a storage_id and a copy of `rpm` with a canonical checksum.'
        with self._download(rpm.location) as input, \
                self._storage.writer() as output:
            log.info(f'Downloading {rpm}')
            # Before committing to the DB, let's standardize on one hash
            # algorithm.  Otherwise, it might happen that two repos may
            # store the same RPM hashed with different algorithms, and thus
            # trigger our "different hashes" detector for a sane RPM.
            canonical_hash = hashlib.new(CANONICAL_HASH)
            for chunk in _verify_chunk_stream(
                _read_chunks(input),
                [rpm.checksum],
                rpm.size,
                rpm.location,
            ):  # May raise a ReportableError
                canonical_hash.update(chunk)
                output.write(chunk)
            rpm = rpm._replace(canonical_checksum=Checksum(
                algorithm=CANONICAL_HASH, hexdigest=canonical_hash.hexdigest(),
            ))

            # Remove the blob if we error before the DB commit below.
            storage_id = output.commit(remove_on_exception=True)

            with self._repo_db_ctx as repo_db:
                db_storage_id = repo_db.maybe_store(
                    self._rpm_table, rpm, storage_id,
                )
                _log_if_storage_ids_differ(rpm, storage_id, db_storage_id)
                # By this point, `maybe_store` would have already asserted
                # that the stored `canonical_checksum` matches ours.  If it
                # did not, something is seriously wrong with our writer code
                # -- we should not be raising a `ReportableError` for that.
                if db_storage_id == storage_id:  # We won the race to store rpm
                    repo_db.commit()  # Our `Rpm` got inserted into the DB.
                else:  # We lost the race to commit `rpm`.
                    # Future: batch removes in Storage if this is slow
                    self._storage.remove(storage_id)
                return db_storage_id, rpm

    def _download_rpms(self, rpms: Iterable[Rpm], shard: RpmShard):
        log.info(f'''`{self._repo_name}` has {len(rpms)} RPMs weighing {
            sum(r.size for r in rpms)
        :,} bytes''')
        storage_id_to_rpm = {}
        # Download in random order to reduce collisions from racing writers.
        for rpm in shuffled(rpms):
            if not shard.in_shard(rpm):
                continue
            with self._repo_db_ctx as db:
                # If we get no `storage_id` back, there are 3 possibilities:
                #  - `rpm.filename` was never seen before.
                #  - `rpm.filename` was seen before, but it was hashed with
                #     different algorithm(s), so we MUST download and
                #     compute the canonical checksum to know if its contents
                #     are the same.
                #  - `rpm.filename` was seen before, **AND** one of the
                #    prior checksums used `rpm.checksum.algorithms`, but
                #    produced a different hash value.  In other words, this
                #    is a `MutableRpmError`, because the same filename must
                #    have had two different contents.  We COULD explicitly
                #    detect this error here, and avoid the download.
                #    However, this severe error should be infrequent, and we
                #    actually get valuable information from the download --
                #    this lets us know whether the file is wrong or the
                #    repodata is wrong.
                storage_id, canonical_checksum = \
                    db.get_rpm_storage_id_and_checksum(self._rpm_table, rpm)
            # If the RPM is already stored with a matching checksum, just
            # update its `.canonical_checksum`.
            if storage_id:
                rpm = rpm._replace(canonical_checksum=canonical_checksum)
            else:  # We have to download the RPM.
                try:
                    with _reportable_http_errors(rpm.location):
                        storage_id, rpm = self._download_rpm(rpm)
                # IMPORTANT: All the classes of errors that we handle below
                # have the property that we would not have stored anything
                # new in the DB, meaning that such failed RPMs will be
                # retried on the next snapshot attempt.
                except ReportableError as ex:
                    # RPM checksum validation errors, scenarios where the
                    # same RPM name occurs with different checksums, etc.
                    storage_id = ex

            # Detect if this RPM filename occurs with different contents.
            if not isinstance(storage_id, ReportableError):
                storage_id = self._detect_mutable_rpms(rpm, storage_id)

            set_new_key(storage_id_to_rpm, storage_id, rpm)

        assert len(storage_id_to_rpm) == sum(shard.in_shard(r) for r in rpms)
        return storage_id_to_rpm

    def _detect_mutable_rpms(self, rpm: Rpm, storage_id: str):
        with self._repo_db_ctx as repo_db:
            all_canonical_checksums = set(repo_db.get_rpm_canonical_checksums(
                self._rpm_table, rpm.filename(),
            ))
        assert all_canonical_checksums, (rpm, storage_id)
        assert all(
            c.algorithm == CANONICAL_HASH for c in all_canonical_checksums
        ), all_canonical_checksums
        all_canonical_checksums.remove(rpm.canonical_checksum)
        deleted_checksums = deleted_mutable_rpms.get(rpm.filename(), set())
        assert rpm.canonical_checksum not in deleted_checksums, \
            f'{rpm} was in deleted_mutable_rpms, but still exists in repos'
        all_canonical_checksums.difference_update(deleted_checksums)
        if all_canonical_checksums:
            # Future: It would be nice to mark all mentions of the filename
            # as bad, but that requires messy updates of multiple
            # `RepoSnapshot`s.  For now, we rely on the fact that the next
            # `snapshot-repos` run will do this anyway.
            return MutableRpmError(
                location=rpm.location,
                storage_id=storage_id,
                checksum=rpm.canonical_checksum,
                other_checksums=all_canonical_checksums,
            )
        return storage_id

    def _commit_repodata_and_cancel_cleanup(
        self,
        repomd: RepoMetadata,
        # We'll replace our IDs by those that actually ended up in the DB
        storage_id_to_repodata: Mapping[str, Repodata],
        # Will retain only those IDs that are unused by the DB and need cleanup
        persist_storage_id_to_repodata: Mapping[str, Repodata],
    ):
        with self._repo_db_ctx as repo_db:
            # We cannot touch `persist_storage_id_to_repodata` in the loop
            # because until the transaction commits, we must be ready to
            # delete all new storage IDs.  So instead, we will construct the
            # post-commit version of that dictionary (i.e. blobs we need to
            # delete even if the transaction lands), in this variable:
            unneeded_storage_id_to_repodata = {}
            for storage_id, repodata in persist_storage_id_to_repodata.items():
                assert not isinstance(storage_id, ReportableError), repodata
                db_storage_id = repo_db.maybe_store(
                    self._repodata_table, repodata, storage_id
                )
                _log_if_storage_ids_differ(repodata, storage_id, db_storage_id)
                if db_storage_id != storage_id:
                    set_new_key(
                        storage_id_to_repodata,
                        db_storage_id,
                        storage_id_to_repodata.pop(storage_id),
                    )
                    set_new_key(
                        unneeded_storage_id_to_repodata, storage_id, repodata,
                    )
            repo_db.store_repomd(self._repo_name, repomd)
            repo_db.commit()
            # The DB commit was successful, and we're about to exit the
            # repo_db context, which might, at worst, raise its own error.
            # Therefore, let's prevent the `finally` cleanup from deleting
            # the blobs whose IDs we just committed to the DB.
            persist_storage_id_to_repodata.clear()
            persist_storage_id_to_repodata.update(
                unneeded_storage_id_to_repodata
            )

    def download(
        self, *,
        rpm_shard: RpmShard = None,  # get all RPMs
        visitors: Iterable['RepoObjectVisitor'] = (),
    ) -> RepoSnapshot:
        'See the top-of-file docblock.'
        if rpm_shard is None:
            rpm_shard = RpmShard(shard=0, modulo=1)
        with self._download('repodata/repomd.xml') as repomd_stream:
            repomd = RepoMetadata.new(xml=repomd_stream.read())
            for visitor in visitors:
                visitor.visit_repomd(repomd)

        # When we store a repodata blob, its ID gets added to this dict.
        # The `finally` clause below will remove any IDs in the list, while
        # `_commit_repodata_and_cancel_cleanup` will clear it on success.
        #
        # ## Rationale for this cleanup logic
        #
        # For any sizable repo, the initial RPM download will be slow.
        #
        # At this point, none of the downloaded repodata is committed to the
        # DB, and all the associated blobs are still subject to
        # auto-cleanup.  The rationale is that if we fail partway through
        # the download, the repo content has likely changed and it's best to
        # redownload the metadata when we retry, rather than to persist some
        # partial and unusable metadata.
        #
        # We do two things to minimize that chances of persisting
        # partial metadata:
        #  (1) Write metadata to the DB in a single transaction.
        #  (2) Keep `remove_unneeded_storage_ids` ready to delete all
        #      newly stored (and thus unreferenced from the DB) repodata
        #      blobs, up until the moment that the transaction commits.
        persist_storage_id_to_repodata = {}
        try:
            # Download the repodata blobs to storage, and add them to
            # `persist_storage_id_to_repodata` to enable automatic cleanup on
            # error via `finally`.
            rpm_set, storage_id_to_repodata = self._download_repodatas(
                repomd, persist_storage_id_to_repodata, visitors
            )

            storage_id_to_rpm = self._download_rpms(rpm_set, rpm_shard)
            # Visitors inspect all RPMs, whether or not they belong to the
            # current shard.  For the RPMs in this shard, visiting after
            # `_download_rpms` allows us to pass in an `Rpm` structure
            # with `.canonical_checksum` set, to better detect identical
            # RPMs from different repos.
            for visitor in visitors:
                for rpm in {
                    **{r.location: r for r in rpm_set},
                    # Post-download Rpm objects override the pre-download ones
                    **{r.location: r for r in storage_id_to_rpm.values()},
                }.values():
                    visitor.visit_rpm(rpm)

            # Commit all the repo metadata, inactivate the `finally` cleanup
            # (except for blobs that we don't want to retain, after all.)
            self._commit_repodata_and_cancel_cleanup(
                repomd, storage_id_to_repodata, persist_storage_id_to_repodata,
            )
        finally:
            if persist_storage_id_to_repodata:
                log.info('Deleting uncommitted blobs, do not Ctrl-C')
            for storage_id in persist_storage_id_to_repodata.keys():
                try:
                    self._storage.remove(storage_id)
                # Yes, catch even KeyboardInterrupt to minimize our litter
                except BaseException:  # pragma: no cover
                    log.exception(f'Failed to remove {storage_id}')

        return RepoSnapshot(
            repomd=repomd,
            storage_id_to_repodata=storage_id_to_repodata,
            storage_id_to_rpm=storage_id_to_rpm,
        )
