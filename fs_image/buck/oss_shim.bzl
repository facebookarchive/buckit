# This file redeclares (and potentially validates) JUST the part of the
# fbcode macro API that is allowed within `fs_image/`.  This way,
# FB-internal contributors will be less likely to accidentally break
# open-source by starting to use un-shimmed features.
load(":oss_shim_impl.bzl", "shim")

def _check_args(rule, args, kwargs, allowed_kwargs):
    if args:
        fail("use kwargs")
    for kwarg in kwargs:
        if kwarg not in allowed_kwargs:
            fail("kwarg {} is not supported by {}".format(
                kwarg,
                rule,
            ))

def _setify(l):
    return {k: 1 for k in l}

_PYTHON_BINARY_KWARGS = _setify(
    ["name", "base_module", "deps", "main_module", "par_style", "srcs"],
)

def python_binary(*args, **kwargs):
    _check_args("python_binary", args, kwargs, _PYTHON_BINARY_KWARGS)
    shim.python_binary(**kwargs)

_PYTHON_LIBRARY_KWARGS = _setify(
    # Future: do we really need `gen_srcs`?
    ["name", "base_module", "deps", "gen_srcs", "resources", "srcs"],
)

def python_library(*args, **kwargs):
    _check_args("python_library", args, kwargs, _PYTHON_LIBRARY_KWARGS)
    shim.python_library(**kwargs)

_PYTHON_UNITTEST_KWARGS = _setify(
    ["name", "base_module", "deps", "main_module", "needed_coverage", "par_style", "resources", "srcs"],
)

def python_unittest(*args, **kwargs):
    _check_args("python_unittest", args, kwargs, _PYTHON_UNITTEST_KWARGS)
    shim.python_unittest(**kwargs)
