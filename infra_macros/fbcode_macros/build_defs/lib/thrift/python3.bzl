"""
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbcode_macros//build_defs:cython_library.bzl", "cython_library")

_CYTHON_TYPES_GENFILES = (
    "types.pxd",
    "types.pyx",
    "types.pyi",
)

_CYTHON_RPC_GENFILES = (
    "services.pxd",
    "services.pyx",
    "services.pyi",
    "services_wrapper.pxd",
    "clients.pyx",
    "clients.pxd",
    "clients.pyi",
    "clients_wrapper.pxd",
)

_CXX_RPC_GENFILES = (
    "services_wrapper.cpp",
    "services_wrapper.h",
    "clients_wrapper.cpp",
    "clients_wrapper.h",
)

_TYPES_SUFFIX = "-types"
_SERVICES_SUFFIX = "-services"
_CLIENTS_SUFFIX = "-clients"

def _get_cpp2_dep(dep):
    if dep.endswith("-py3"):
        dep = dep[:-len("-py3")]
    return dep + "-cpp2"

def _thrift_name(thrift_src):
    return paths.split_extension(paths.basename(thrift_src))[0]

def _generated(sources, py3_namespace, src, thrift_src):
    thrift_src = src_and_dep_helpers.get_source_name(thrift_src)
    thrift_name = _thrift_name(thrift_src)
    thrift_package = paths.join(thrift_name, src)
    if src in _CXX_RPC_GENFILES:
        full_src = thrift_package
        dst = paths.join("gen-py3", full_src)
    else:
        full_src = paths.join(py3_namespace.replace(".", "/"), thrift_package)
        dst = thrift_package
    return (sources[thrift_src][full_src], dst)

def _get_lang():
    return "py3"

def _get_compiler_lang():
    return "mstch_py3"

def _get_names():
    return ("py3",)

def _get_options(base_path, parsed_options):
    options = {
        "include_prefix": base_path,
    }
    options.update(parsed_options)
    return options

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        py3_namespace = "",
        **_kwargs):
    """
    Return a dict of all generated thrift sources, mapping the logical
    language-specific name to the path of the generated source relative
    to the thrift compiler output directory.

    cpp files and cython files have different paths because of
    their different compilation behaviors
    """
    _ignore = base_path
    _ignore = name
    _ignore = options
    thrift_name = _thrift_name(thrift_src)
    package = paths.join(py3_namespace, thrift_name).replace(".", "/")

    # If there are services defined then there will be services/clients files
    # and cpp files.
    if services:
        cython_genfiles = _CYTHON_TYPES_GENFILES + _CYTHON_RPC_GENFILES
        cpp_genfiles = _CXX_RPC_GENFILES
    else:
        cython_genfiles = _CYTHON_TYPES_GENFILES
        cpp_genfiles = ()

    cython_paths = [
        paths.join(package, genfile)
        for genfile in cython_genfiles
    ]

    cpp_paths = [
        paths.join(thrift_name, genfile)
        for genfile in cpp_genfiles
    ]

    return {
        path: paths.join("gen-py3", path)
        for src_paths in (cython_paths, cpp_paths)
        for path in src_paths
    }

def _gen_rule_thrift_types(
        name,
        sources,
        thrift_srcs,
        namespace,
        fdeps,
        visibility):
    """Generates rules for Thrift types."""

    srcs = {}
    headers = {}
    types = {}

    for src in thrift_srcs:
        srcs.update((_generated(sources, namespace, "types.pyx", src),))
        headers.update((_generated(sources, namespace, "types.pxd", src),))
        types.update((_generated(sources, namespace, "types.pyi", src),))

    cython_library(
        name = name + _TYPES_SUFFIX,
        package = namespace,
        srcs = srcs,
        headers = headers,
        types = types,
        cpp_deps = [":" + _get_cpp2_dep(name)] + [
            _get_cpp2_dep(d)
            for d in fdeps
        ],
        deps = [
            thrift_common.get_thrift_dep_target("thrift/lib/py3", "exceptions"),
            thrift_common.get_thrift_dep_target("thrift/lib/py3", "std_libcpp"),
            thrift_common.get_thrift_dep_target("thrift/lib/py3", "types"),
        ] + [d + _TYPES_SUFFIX for d in fdeps],
        cpp_compiler_flags = ["-fno-strict-aliasing"],
        visibility = visibility,
    )

def _gen_rule_thrift_services(
        name,
        sources,
        thrift_srcs,
        namespace,
        fdeps,
        visibility):
    """Generate rules for Thrift Services"""

    # Services and support
    services_srcs = {}
    services_headers = {}
    services_typing = {}

    cython_api = {}

    for src, services in thrift_srcs.items():
        if not services:
            continue
        services_srcs.update((_generated(sources, namespace, "services.pyx", src),))
        services_srcs.update((_generated(sources, namespace, "services_wrapper.cpp", src),))
        services_headers.update((_generated(sources, namespace, "services.pxd", src),))
        services_headers.update((_generated(sources, namespace, "services_wrapper.pxd", src),))
        services_headers.update((_generated(sources, namespace, "services_wrapper.h", src),))
        services_typing.update((_generated(sources, namespace, "services.pyi", src),))

        # Build out a cython_api dict, to place the _api.h files inside
        # the gen-py3/ root so the c++ code can find it
        thrift_name = _thrift_name(src)
        module_path = paths.join(thrift_name, "services")
        dst = paths.join("gen-py3", module_path)
        cython_api[module_path] = dst

    cython_library(
        name = name + _SERVICES_SUFFIX,
        package = namespace,
        srcs = services_srcs,
        headers = services_headers,
        types = services_typing,
        cpp_deps = [
            ":" + _get_cpp2_dep(name),
        ],
        deps = [
            ":" + name + _TYPES_SUFFIX,
            thrift_common.get_thrift_dep_target("thrift/lib/py3", "server"),
        ] + [d + _SERVICES_SUFFIX for d in fdeps],
        cpp_compiler_flags = ["-fno-strict-aliasing"],
        api = cython_api,
        visibility = visibility,
    )

def _gen_rule_thrift_clients(
        name,
        sources,
        thrift_srcs,
        namespace,
        fdeps,
        visibility):
    # Clients and support
    clients_srcs = {}
    clients_headers = {}
    clients_typing = {}

    for src, services in thrift_srcs.items():
        if not services:
            continue
        clients_srcs.update((_generated(sources, namespace, "clients.pyx", src),))
        clients_srcs.update((_generated(sources, namespace, "clients_wrapper.cpp", src),))
        clients_headers.update((_generated(sources, namespace, "clients.pxd", src),))
        clients_headers.update((_generated(sources, namespace, "clients_wrapper.pxd", src),))
        clients_headers.update((_generated(sources, namespace, "clients_wrapper.h", src),))
        clients_typing.update((_generated(sources, namespace, "clients.pyi", src),))

    cython_library(
        name = name + _CLIENTS_SUFFIX,
        package = namespace,
        srcs = clients_srcs,
        headers = clients_headers,
        types = clients_typing,
        cpp_deps = [
            ":" + _get_cpp2_dep(name),
        ],
        deps = [
            ":" + name + _TYPES_SUFFIX,
            thrift_common.get_thrift_dep_target("thrift/lib/py3", "client"),
        ] + [d + _CLIENTS_SUFFIX for d in fdeps],
        cpp_compiler_flags = ["-fno-strict-aliasing"],
        visibility = visibility,
    )

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources,
        deps,
        py3_namespace = "",
        visibility = None,
        **_kwargs):
    """
    Generate the language-specific library rule (and any extra necessary
    rules).
    """
    _ignore = base_path
    _ignore = options

    # Strip off the gen target prefixes, from .thrift sources
    thrift_srcs = {
        src_and_dep_helpers.get_source_name(thrift_src): services
        for thrift_src, services in thrift_srcs.items()
    }

    for gen_func in (
        _gen_rule_thrift_types,
        _gen_rule_thrift_services,
        _gen_rule_thrift_clients,
    ):
        gen_func(
            name,
            sources,
            thrift_srcs,
            py3_namespace,
            deps,
            visibility = visibility,
        )

_POST_PROCESS_COMMAND_NO_NAMESPACE = """
Compiling {src} did not generate source in {types_path}
Does the 'namespace py3' directive in the thrift file match the py3_namespace specified in the TARGETS file?
  py3_namespace is {py3_namespace_repr}
  thrift file should not contain any 'namespace py3' directive
""".strip()

_POST_PROCESS_COMMAND_WITH_NAMESPACE = """
Compiling {src} did not generate source in {types_path}
Does the 'namespace py3' directive in the thrift file match the py3_namespace specified in the TARGETS file?
  py3_namespace is {py3_namespace_repr}
  thrift file should contain 'namespace py3 {py3_namespace}'
""".strip()

def _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        py3_namespace = "",
        **_kwargs):
    # The location of the generated thrift files depends on the value of
    # the "namespace py3" directive in the .thrift file, and we
    # unfortunately don't know what this value is.  After compilation, make
    # sure the types.pyx file exists in the location we expect.  If not,
    # there is probably a mismatch between the py3_namespace parameter in the
    # TARGETS file and the "namespace py3" directive in the .thrift file.
    thrift_name = _thrift_name(thrift_src)
    package = paths.join(py3_namespace, thrift_name).replace(".", "/")
    output_dir = paths.join(out_dir, "gen-py3", package)
    types_path = paths.join(output_dir, "types.pyx")

    if py3_namespace:
        msg_template = _POST_PROCESS_COMMAND_WITH_NAMESPACE
    else:
        msg_template = _POST_PROCESS_COMMAND_NO_NAMESPACE

    msg = msg_template.format(
        src = paths.join(base_path, thrift_src),
        types_path = types_path,
        py3_namespace_repr = repr(py3_namespace),
        py3_namespace = py3_namespace,
    ).splitlines()

    cmd = "if [ ! -f {} ]; then ".format(types_path)
    for line in msg:
        cmd += ' echo "{}" >&2;'.format(line)
    cmd += " false; fi"

    return cmd

python3_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_options = _get_options,
    get_compiler_lang = _get_compiler_lang,
    get_names = _get_names,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
    get_postprocess_command = _get_postprocess_command,
)
