#!/bin/bash -uex
#
# `test_parse_dump.py` also checks that we are able to parse the output of a
# live `btrfs receive --dump`, but the specific **sequence** of lines it
# produces to represent the filesystem is an implementation detail, and may
# change, since there is not a _uniquely_ correct way of doing it.
#
# So instead of testing parsing on a live `print_demo_dump.sh`, which would
# always be at risk of breaking arbitrarily, we do two things:
#  - Via this script, we freeze a sequence from one point in time just
#    for the sake of having a parse-only test.
#  - To test the semantics of the parsed data, we test applying a live
#    sequence to a mock filesystem, which should always give the same result.
#
me=$(readlink -f "$0")
d_tests=$(dirname "$me")
d_btrfs_diff=$(dirname "$d_tests")
d_container_image=$(dirname "$d_btrfs_diff")
d_artifacts=$("$d_container_image"/artifacts_dir.py)
d_volume=$("$d_container_image"/volume_for_repo.py "$d_artifacts" 1e8)
cd "$d_volume"
(
  date +%s   # for `build_start_time`
  sudo "$d_tests/print_demo_dump.sh"
  date +%s   # for `build_end_time`
) > "$d_tests/gold_print_demo_dump.txt"
