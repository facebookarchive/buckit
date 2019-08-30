load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")
load("@fbcode_macros//build_defs:python_library.bzl", "python_library")
load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")

shim = struct(
    python_binary = python_binary,
    python_library = python_library,
    python_unittest = python_unittest,
)
