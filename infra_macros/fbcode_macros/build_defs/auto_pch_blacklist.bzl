# Packages that should not get autopch headers
load("@bazel_skylib//lib:new_sets.bzl", "sets")

auto_pch_blacklist = sets.make([
])
