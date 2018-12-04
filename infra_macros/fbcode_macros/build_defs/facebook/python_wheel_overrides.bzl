#!/usr/bin/env python

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:config.bzl", "config")

# Big tuple of tuples used to generate a dict of all the external_deps /
# TP2 dependencies mapped to the new PyFI //python/wheel TARGET.
# These will be use with python_* TARGETS to allow for a cleaner migration to PyFI

OVERRIDES = (
    # TP2 Name, PyFI Target Name
    ("Jinja2", "jinja2"),
    ("MarkupSafe", "markupsafe"),
    ("PyYAML", "pyyaml"),
    ("Pygments", "pygments"),  # TP2 has duplicates (See pygments)
    ("Shapely", "shapely"),
    ("aiohttp", "aiohttp"),
    ("async-timeout", "async-timeout"),
    ("certifi", "certifi"),
    ("python-chardet", "chardet"),
    ("colorama", "colorama"),
    ("coverage", "coverage"),
    ("decorator", "decorator"),
    ("funcsigs", "funcsigs"),
    ("functools32", "functools32"),
    ("html5lib", "html5lib"),
    ("idna", "idna"),
    ("idna-ssl", "idna-ssl"),
    ("ig-aiohttp", "aiohttp"),
    ("ig-multidict", "multidict"),
    ("ig-yarl", "yarl"),
    ("ipython", "ipython"),
    ("ipython_genutils", "ipython-genutils"),
    ("jsonpickle", "jsonpickle"),
    ("jsonschema", "jsonschema"),
    ("mock", "mock"),
    ("multidict", "multidict"),
    ("mypy", "mypy"),
    ("mypy_extensions", "mypy-extensions"),
    ("pathlib2", "pathlib2"),
    ("pexpect", "pexpect"),
    ("pexpect-u", "pexpect"),
    ("ply", "ply"),
    ("prompt-toolkit", "prompt-toolkit"),
    ("psutil", "psutil"),
    ("ptyprocess", "ptyprocess"),
    ("pycparser", "pycparser"),
    ("pygments", "pygments"),  # TP2 has duplicates (see Pygments)
    ("pyparsing", "pyparsing"),
    ("python-attrs", "attrs"),
    ("python-cffi", "cffi"),
    ("python-chardet", "chardet"),
    ("python-click", "click"),  # We have a hacked unicode_literals 7.0.dev release
    ("python-dateutil", "python-dateutil"),
    ("python-enum34", "enum34"),
    ("python-future", "future"),
    ("python-idna", "idna"),
    ("python-ipaddress", "ipaddress"),
    ("python-munch", "munch"),
    ("python-requests", "requests"),
    ("pytz", "pytz"),
    ("retype", "retype"),
    ("setuptools", "setuptools"),
    ("singledispatch", "singledispatch"),
    ("six", "six"),
    ("traitlets", "traitlets"),
    ("typing", "typing"),
    ("typed-ast", "typed-ast"),
    ("urllib3", "urllib3"),
    ("wcwidth", "wcwidth"),
    ("yarl", "yarl"),
)

_PYFI_SUPPORTED_PLATFORMS = (
    "gcc-5-glibc-2.23",
    "gcc-5-glibc-2.23-aarch64",
    "platform007",
    "platform007-aarch64",
)

def _generate_pyfi_overrides(overrides):
    # type: (Tuple[str, str, str]) -> Dict[Union[str, Tuple[Optional[str], ...]], str]
    """Generate str key mapping of TP2 name to PyFI TARGET name"""
    pyfi_overrides = {}
    for tp2_name, pyfi_name in overrides:
        pyfi_overrides[tp2_name] = target_utils.RootRuleTarget(
            paths.join("python/wheel", pyfi_name),
            pyfi_name,
        )

    return pyfi_overrides

def _should_use_overrides():
    return bool(config.get_pyfi_overrides_path())

_PYFI_OVERRIDES = _generate_pyfi_overrides(OVERRIDES)

python_wheel_overrides = struct(
    PYFI_OVERRIDES = _PYFI_OVERRIDES,
    PYFI_SUPPORTED_PLATFORMS = _PYFI_SUPPORTED_PLATFORMS,
    should_use_overrides = _should_use_overrides,
)
