#!/bin/bash -ue
#
# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.
#
set -o pipefail
#
# Executed under `sudo` by `get_volume_for_current_repo()`. Makes sure that
# the given btrfs volume path is tagged with the absolute path of the source
# repo, and is not used by any other source repo.
#
# CAREFUL: This operation is not atomic, so if there is any chance it might
# run concurrently, be sure to wrap this script with `flock`.
#

min_bytes="${1:?argument 1 resizes the volume to have this many free bytes}"
image="${2:?argument 2 must be a path to a btrfs image, which may get erased}"
volume="${3:?argument 3 must be the path for the btrfs volume mount}"

mount_image() {
  echo "Mounting btrfs $image at $volume"
  # Explicitly set filesystem type to detect shenanigans.
  mount -t btrfs -o loop,discard,nobarrier "$image" "$volume"
}

format_image() {
  echo "Formatting empty btrfs of $min_bytes bytes at $image"
  local min_useful_fs_size=$((175 * 1024 * 1024))
  if [[ "$min_bytes" -lt "$min_useful_fs_size" ]] ; then
    # Would get:
    #  < 100MB: ERROR: not enough free space to allocate chunk
    #  < 175MB: ERROR: unable to resize '_foo/volume': Invalid argument
    echo "btrfs filesystems of < $min_useful_fs_size do not work well"
    exit 1
  fi
  truncate -s "$min_bytes" "$image"
  mkfs.btrfs "$image"
}

ensure_mounted() {
  mkdir -p "$volume"
  # Don't bother checking if $volume is another kind of mount, since we will
  # just proceed to mount over it.
  if [[ "$(findmnt --noheadings --output FSTYPE "$volume")" != btrfs ]] ; then
    # Do a checksum scrub -- since we run with nobarrier and --direct-io, it
    # is entirely possible that a power failure will corrupt the image.
    btrfs check --check-data-csum "$image" || format_image
    # If it looks like we have a valid image, just re-use it. This allows us
    # to recover built images after a restart.
    mount_image || (format_image && mount_image)
  fi
  local loop_dev
  loop_dev=$(findmnt --noheadings --output SOURCE "$volume")
  # This helps perf and avoids doubling our usage of buffer cache.
  losetup --direct-io=on "$loop_dev" ||
    echo "Could not enable --direct-io for $loop_dev, expect worse performance"

  local free_bytes
  free_bytes=$(findmnt --bytes --noheadings --output AVAIL "$volume")
  local growth_bytes
  growth_bytes=$((min_bytes - free_bytes))

  if [[ "$growth_bytes" -gt 0 ]] ; then
    echo "Growing $image by $growth_bytes bytes"
    local old_bytes
    old_bytes=$(stat --format=%s "$image")
    local new_bytes
    new_bytes=$((old_bytes + growth_bytes))
    # Paranoid assertions in case of integer overflow or similar bugs
    [[ "$new_bytes" -gt "$old_bytes" ]]
    [[ $((new_bytes - growth_bytes)) -eq "$old_bytes" ]]
    truncate -s "$new_bytes" "$image"
    losetup --set-capacity "$loop_dev"
    btrfs filesystem resize max "$volume"
  fi
}

ensure_mounted 1>&2  # In Buck, stderr is more useful
