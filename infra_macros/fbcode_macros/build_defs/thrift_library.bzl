load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")

_PY_REMOTES_EXTERNAL_DEPS = (
    "python-future",
    "six",
)

def py_remote_binaries(
        base_path,
        name,
        thrift_srcs,
        base_module,
        visibility,
        include_sr = False):
    """
    Generate binaries for py-remote support
    """

    # Find and normalize the base module.
    if base_module == None:
        base_module = base_path
    base_module = base_module.replace("/", ".")

    for thrift_src, services in thrift_srcs.items():
        thrift_base = (
            paths.split_extension(
                paths.basename(src_and_dep_helpers.get_source_name(thrift_src)),
            )[0]
        )
        for service in services:
            if include_sr:
                sr_rule = "//thrift/facebook/remote/sr:remote"
            else:
                sr_rule = "//thrift/lib/py/util:remote"
            main_module = ".".join([
                element
                for element in [
                    base_module,
                    thrift_base,
                    service + "-remote",
                ]
                if element
            ])
            python_binary(
                name = "{}-{}-pyremote".format(name, service),
                visibility = visibility,
                py_version = "<3",
                base_module = "",
                main_module = main_module,
                deps = [
                    ":{}-py".format(name),
                    sr_rule,
                ],
                external_deps = _PY_REMOTES_EXTERNAL_DEPS,
            )
