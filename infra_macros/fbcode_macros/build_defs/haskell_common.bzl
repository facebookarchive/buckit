# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_boolean", "read_list")

def _read_hs_debug():
    return read_boolean("fbcode", "hs_debug", False)

def _read_hs_eventlog():
    return read_boolean("fbcode", "hs_eventlog", False)

def _read_hs_profile():
    return read_boolean("fbcode", "hs_profile", False)

def _read_extra_ghc_compiler_flags():
    return read_list("haskell", "extra_compiler_flags", [], " ")

def _read_extra_ghc_linker_flags():
    return read_list("haskell", "extra_linker_flags", [], " ")

haskell_common = struct(
    read_extra_ghc_compiler_flags = _read_extra_ghc_compiler_flags,
    read_extra_ghc_linker_flags = _read_extra_ghc_linker_flags,
    read_hs_debug = _read_hs_debug,
    read_hs_eventlog = _read_hs_eventlog,
    read_hs_profile = _read_hs_profile,
)
