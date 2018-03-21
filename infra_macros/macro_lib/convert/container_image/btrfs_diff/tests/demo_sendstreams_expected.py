#!/usr/bin/env python3
'''
`demo_sendstreams.py` performs filesystem operations to generate some
send-stream data, this records the send-stream we would expect to see from
these operations.

Any time you run `demo_sendstreams` with `--update-gold`, you need to update
the constants below.  The actual send-stream may need to change if the
`btrfs send` implementation changes.
'''
import logging
import os

from typing import List, Sequence, Tuple

from ..send_stream import (
    get_frequency_of_selinux_xattrs, ItemFilters, SendStreamItem,
    SendStreamItems,
)
from ..subvol_path import SubvolPath

# Update these constants to make the tests pass again after running
# `demo_sendstreams` with `--update-gold`.
UUID_CREATE = b'2e178b7b-b005-b545-9de3-8c9f0c7881fd'
TRANSID_CREATE = 3850
UUID_MUTATE = b'9849f057-eb81-304d-a50d-76997da610f5'
TRANSID_MUTATE = 3853
# Take a `oNUM-NUM-NUM` file from the send-stream, and use the middle number.
TEMP_PATH_MIDDLES = {'create_ops': 3848, 'mutate_ops': 3852}
# I have never seen this initial value change. First number in `oN-N-N`.
TEMP_PATH_COUNTER = 256


def get_filtered_and_expected_items(
    items: Sequence[SendStreamItem],
    build_start_time: float, build_end_time: float,
) -> Tuple[List[SendStreamItem], List[SendStreamItem]]:

    # Our test program does not touch the SELinux context, so if it's
    # set, it will be set to the default, and we can just filter out the
    # most frequent value.  We don't want to drop all SELinux attributes
    # blindly because having varying contexts suggests something broken
    # about the test or our environment.
    selinux_freqs = get_frequency_of_selinux_xattrs(items)
    assert len(selinux_freqs) > 0  # Our `gold` has SELinux attrs
    max_name, _count = max(selinux_freqs.items(), key=lambda p: p[1])
    logging.info(f'This test ignores SELinux xattrs set to {max_name}')
    filtered_items = items
    filtered_items = ItemFilters.selinux_xattr(
        filtered_items,
        discard_fn=lambda _path, ctx: ctx == max_name,
    )
    filtered_items = ItemFilters.normalize_utimes(
        filtered_items, start_time=build_start_time, end_time=build_end_time,
    )
    filtered_items = list(filtered_items)

    di = SendStreamItems

    def p(path):
        if isinstance(path, str):  # forgive missing `b`s, it's a test
            path = path.encode()
        return SubvolPath._new(path)

    def chown(path):
        return di.chown(path=p(path), gid=0, uid=0)

    def chmod(path, mode=0o644):
        return di.chmod(path=p(path), mode=mode)

    def utimes(path):
        return di.utimes(
            path=p(path),
            atime=build_start_time,
            mtime=build_start_time,
            ctime=build_start_time,
        )

    def base_metadata(path, mode=0o644):
        return [chown(path), chmod(path, mode), utimes(path)]

    # Future: if we end up doing a lot of mid-list insertions, we can
    # autogenerate the temporary names to match what btrfs does.
    def and_rename(item, real_name, utimes_parent=True):
        yield item
        renamed_item = di.rename(
            path=item.path,
            dest=p(
                os.path.join(os.path.dirname(bytes(item.path)), real_name)
            ),
        )
        yield renamed_item
        if utimes_parent:  # Rarely, `btrfs send` breaks the pattern.
            yield utimes(os.path.dirname(bytes(renamed_item.dest)))

    def temp_path(prefix):
        global TEMP_PATH_COUNTER
        TEMP_PATH_COUNTER += 1
        mid = TEMP_PATH_MIDDLES[prefix]
        return p(f'{prefix}/o{TEMP_PATH_COUNTER}-{mid}-0')

    return filtered_items, [
        di.subvol(
            path=p('create_ops'), uuid=UUID_CREATE, transid=TRANSID_CREATE,
        ),
        *base_metadata('create_ops', mode=0o755),

        *and_rename(di.mkdir(path=temp_path('create_ops')), b'hello'),
        di.set_xattr(
            path=p('create_ops/hello'),
            name=b'user.test_attr',
            data=b'chickens',
        ),
        *base_metadata('create_ops/hello', mode=0o755),

        *and_rename(
            di.mkdir(path=temp_path('create_ops')), b'dir_to_remove'
        ),
        *base_metadata('create_ops/dir_to_remove', mode=0o755),

        *and_rename(
            di.mkfile(path=temp_path('create_ops')), b'goodbye',
            utimes_parent=False,
        ),
        di.link(
            path=p('create_ops/hello/world'), dest=p('create_ops/goodbye'),
        ),
        utimes('create_ops'),
        utimes('create_ops/hello'),
        di.truncate(path=p('create_ops/goodbye'), size=0),
        *base_metadata('create_ops/goodbye'),

        *and_rename(di.mknod(
            path=temp_path('create_ops'), mode=0o60600, dev=0x7a539b7,
        ), b'buffered'),
        *base_metadata('create_ops/buffered', mode=0o600),

        *and_rename(di.mknod(
            path=temp_path('create_ops'), mode=0o20644, dev=0x7a539b7,
        ), b'unbuffered'),
        *base_metadata('create_ops/unbuffered'),

        *and_rename(di.mkfifo(path=temp_path('create_ops')), b'fifo'),
        *base_metadata('create_ops/fifo'),

        *and_rename(
            di.mksock(path=temp_path('create_ops')), b'unix_sock',
        ),
        *base_metadata('create_ops/unix_sock', mode=0o755),

        *and_rename(di.symlink(
            path=temp_path('create_ops'), dest=b'hello/world',
        ), b'bye_symlink'),
        chown('create_ops/bye_symlink'),
        utimes('create_ops/bye_symlink'),

        *and_rename(
            di.mkfile(path=temp_path('create_ops')), b'1MB_nuls',
        ),
        di.update_extent(
            path=p('create_ops/1MB_nuls'), offset=0, len=2**20,
        ),
        di.truncate(path=p('create_ops/1MB_nuls'), size=2**20),
        *base_metadata('create_ops/1MB_nuls'),

        *and_rename(
            di.mkfile(path=temp_path('create_ops')), b'1MB_nuls_clone',
        ),
        di.clone(
            path=p('create_ops/1MB_nuls_clone'), offset=0, len=2**20,
            from_uuid=b'', from_transid=b'',
            from_path=p('create_ops/1MB_nuls'), clone_offset=0,
        ),
        di.truncate(path=p('create_ops/1MB_nuls_clone'), size=2**20),
        *base_metadata('create_ops/1MB_nuls_clone'),

        *and_rename(
            di.mkfile(path=temp_path('create_ops')), b'zeros_hole_zeros',
        ),
        di.update_extent(
            path=p('create_ops/zeros_hole_zeros'), offset=0, len=16384,
        ),
        di.update_extent(
            path=p('create_ops/zeros_hole_zeros'), offset=32768, len=16384,
        ),
        di.truncate(path=p('create_ops/zeros_hole_zeros'), size=49152),
        *base_metadata('create_ops/zeros_hole_zeros'),

        di.snapshot(
            path=p('mutate_ops'),
            uuid=UUID_MUTATE,
            transid=TRANSID_MUTATE,
            parent_uuid=UUID_CREATE,
            parent_transid=TRANSID_CREATE,
        ),
        utimes('mutate_ops'),
        di.rename(
            path=p('mutate_ops/hello'), dest=p('mutate_ops/hello_renamed'),
        ),
        utimes('mutate_ops'),
        utimes('mutate_ops'),  # `btrfs send` is not so parsimonious

        di.remove_xattr(
            path=p('mutate_ops/hello_renamed'), name=b'user.test_attr',
        ),
        utimes('mutate_ops/hello_renamed'),

        di.rmdir(path=p('mutate_ops/dir_to_remove')),
        utimes('mutate_ops'),

        di.link(
            path=p('mutate_ops/farewell'), dest=p('mutate_ops/goodbye'),
        ),
        di.unlink(path=p('mutate_ops/goodbye')),
        di.unlink(path=p('mutate_ops/hello_renamed/world')),
        utimes('mutate_ops'),
        utimes('mutate_ops'),
        utimes('mutate_ops/hello_renamed'),
        di.truncate(path=p('mutate_ops/farewell'), size=0),
        utimes('mutate_ops/farewell'),

        *and_rename(
            di.mkfile(path=temp_path('mutate_ops')), b'hello_renamed/een',
        ),
        di.update_extent(
            path=p('mutate_ops/hello_renamed/een'), offset=0, len=5,
        ),
        di.truncate(path=p('mutate_ops/hello_renamed/een'), size=5),
        *base_metadata('mutate_ops/hello_renamed/een'),
    ]
