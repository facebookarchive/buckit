# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

# A simple definitions file that lets us bootstrap the
# macros library.

load(":macros.bzl", "get_converted_rules")
load(
    "@fbcode_macros//build_defs:export_files.bzl",
    _buck_export_file = "buck_export_file",
    _export_file = "export_file",
    _export_files = "export_files",
)
load("@fbcode_macros//build_defs:custom_unittest.bzl", _custom_unittest = "custom_unittest")
load("@fbcode_macros//build_defs:dewey_artifact.bzl", _dewey_artifact = "dewey_artifact")
load("@fbcode_macros//build_defs:java_binary.bzl", _java_binary = "java_binary")
load("@fbcode_macros//build_defs:java_library.bzl", _java_library = "java_library")
load("@fbcode_macros//build_defs:java_shaded_jar.bzl", _java_shaded_jar = "java_shaded_jar")
load("@fbcode_macros//build_defs:java_test.bzl", _java_test = "java_test")
load(
    "@fbcode_macros//build_defs:native_rules.bzl",
    _buck_command_alias = "buck_command_alias",
    _buck_filegroup = "buck_filegroup",
    _buck_genrule = "buck_genrule",
    _buck_python_library = "buck_python_library",
    _buck_sh_binary = "buck_sh_binary",
    _buck_sh_test = "buck_sh_test",
    _buck_zip_file = "buck_zip_file",
    _cxx_genrule = "cxx_genrule",
    _remote_file = "remote_file",
    _test_suite = "test_suite",
    _versioned_alias = "versioned_alias",
)
load("@fbcode_macros//build_defs:scala_library.bzl", _scala_library = "scala_library")
load("@fbcode_macros//build_defs:thrift_library.bzl", _thrift_library = "thrift_library")

# Starlark reexports
buck_command_alias = _buck_command_alias
buck_export_file = _buck_export_file
buck_filegroup = _buck_filegroup
buck_genrule = _buck_genrule
buck_python_library = _buck_python_library
buck_sh_binary = _buck_sh_binary
buck_sh_test = _buck_sh_test
buck_zip_file = _buck_zip_file
custom_unittest = _custom_unittest
cxx_genrule = _cxx_genrule
dewey_artifact = _dewey_artifact
export_file = _export_file
export_files = _export_files
java_binary = _java_binary
java_library = _java_library
java_shaded_jar = _java_shaded_jar
java_test = _java_test
remote_file = _remote_file
scala_library = _scala_library
test_suite = _test_suite
thrift_library = _thrift_library
versioned_alias = _versioned_alias

_do_not_import = [
    "buck_command_alias",
    "buck_export_file",
    "buck_filegroup",
    "buck_genrule",
    "buck_python_library",
    "buck_sh_binary",
    "buck_sh_test",
    "buck_zip_file",
    "custom_unittest",
    "cxx_genrule",
    "dewey_artifact",
    "export_file",
    "export_files",
    "java_binary",
    "java_library",
    "java_shaded_jar",
    "java_test",
    "remote_file",
    "scala_library",
    "test_suite",
    "thrift_library",
    "versioned_alias",
]

load_symbols({n: t for n, t in get_converted_rules().items() if n not in _do_not_import})
