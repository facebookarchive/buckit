#!/bin/bash -uex
#
# The intent of this script is to exercise all the 20 item types that can
# currently be emitted by `btrfs send`.
#
# After running this as root from inside the per-repo btrfs volume,
# `test_parse_dump.py` compares the parsed output to what we expect on the
# basis of this script.
#
# To test this manually, you'll want to run this from inside a btrfs
# subvolume.  If you've built any iamges, you should have one at
# `buck-image-out/volume/`.
#
#   cd buck-image-out/volume/
#   sudo PATH_TO/print_create_ops.sh | less -S
#
# IMPORTANT: Be sure not to print anything to stdout except for the btrfs
# stream.  Use `1>&2` redirects as needed.

# An absolute path is required for cleanup
temp_dir=$PWD/$(mktemp -p . -d)

# Trap-based cleanup is the most robust we can do.
subvols_to_delete=()
cleanup() {
  for subvol_to_delete in "${subvols_to_delete[@]}" ; do
    btrfs subvolume delete "$subvol_to_delete" 1>&2
  done
  rmdir "$temp_dir"
}
trap cleanup EXIT

cd "$temp_dir"


# $1 is the subvolume path, other args are options for `btrfs send`
make_read_only_and_dump_subvolume() {
  local subvol_path=${1:?argument 1 must be the subvolume path}
  shift

  btrfs property set -ts "$subvol_path" ro true

  # Btrfs bug #25329702: in some cases, a `send` without a sync will violate
  # read-after-write consistency and send a "past" view of the filesystem.
  # Do this on the read-only filesystem to improve consistency.
  btrfs filesystem sync "$subvol_path"

  # Btrfs bug #25379871: our 4.6 kernels have an experimental xattr caching
  # patch, which is broken, and results in xattrs not showing up in the `send`
  # stream unless that metadata is `fsync`ed.  For some dogscience reason,
  # `getfattr` on a file actually triggers such an `fsync`. We do this on a
  # read-only filesystem to improve consistency.
  if [[ "$(uname -r)" == 4.6.* ]] ; then
    getfattr --no-dereference --recursive "$subvol_path" > /dev/null
  fi

  btrfs send "$@" "$subvol_path" | btrfs receive --dump
}


btrfs subvolume create create_ops 1>&2            # subvol
# An absolute path is required for cleanup
subvols_to_delete+=("$PWD/create_ops")
(
  cd create_ops/

  # Due to an odd `btrfs send` implementation detail, creating a file or
  # directory emits a rename from a temporary name to the final one.
  mkdir hello                                       # mkdir,rename
  mkdir dir_to_remove
  touch hello/world                                 # mkfile,utimes,chmod,chown
  setfattr -n user.test_attr -v chickens hello/     # set_xattr
  mknod buffered b 1337 31415                       # mknod
  mknod unbuffered c 1337 31415
  mkfifo fifo                                       # mkfifo
  nc -l -U unix_sock &                              # mksock
  while [[ ! -e unix_sock ]] ; do
    sleep 0.1
  done
  kill %1
  ln hello/world goodbye                            # link
  ln -s hello/world goodbye_symbolic                # symlink
  dd if=/dev/zero of=1MB_nuls bs=1024 count=1024    # update_extent
  cp --reflink=always 1MB_nuls 1MB_nuls_clone       # clone

  # Make a file with a 16KB hole in the middle.
  dd if=/dev/zero of=zeros_hole_zeros bs=1024 count=16
  truncate -s $((32 * 1024)) zeros_hole_zeros
  dd if=/dev/zero bs=1024 count=16 >> zeros_hole_zeros
)
# `--no-data` saves IOPs. Side effect: `update_extent` instead of `write`.
make_read_only_and_dump_subvolume create_ops --no-data


btrfs subvolume snapshot create_ops mutate_ops 1>&2 # snapshot
# An absolute path is required for cleanup
subvols_to_delete+=("$PWD/mutate_ops")
(
  cd mutate_ops/

  rm hello/world                                    # unlink
  rmdir dir_to_remove/                              # rmdir
  setfattr --remove=user.test_attr hello/           # remove_xattr
  # You would think this would emit a `rename`, but apparently the resulting
  # diff instead `link`s to the new location, and unlinks the old.
  mv goodbye farewell                               # NOT a rename... {,un}link
  mv hello/ hello_renamed/                          # yes, a rename!
  echo push > hello_renamed/een                     # write
)

make_read_only_and_dump_subvolume mutate_ops -p create_ops
