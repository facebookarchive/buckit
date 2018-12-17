"""
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool")

_STATIC_REFLECTION_SUFFIXES = [
    "",
    "_enum",
    "_union",
    "_struct",
    "_constant",
    "_service",
    "_types",
    "_all",
]

_TYPES_HEADER = 0
_TYPES_SOURCE = 1
_CLIENTS_HEADER = 2
_CLIENTS_SOURCE = 3
_SERVICES_HEADER = 4
_SERVICES_SOURCE = 5

_SUFFIXES = [
    ("_constants.h", _TYPES_HEADER),
    ("_constants.cpp", _TYPES_SOURCE),
    ("_types.h", _TYPES_HEADER),
    ("_types.tcc", _TYPES_HEADER),
    ("_types.cpp", _TYPES_SOURCE),
    ("_data.h", _TYPES_HEADER),
    ("_data.cpp", _TYPES_SOURCE),
    ("_layouts.h", _TYPES_HEADER),
    ("_layouts.cpp", _TYPES_SOURCE),
    ("_types_custom_protocol.h", _TYPES_HEADER),
] + [
    ("_fatal%s.h" % suffix, _TYPES_HEADER)
    for suffix in _STATIC_REFLECTION_SUFFIXES
] + [
    ("AsyncClient.h", _CLIENTS_HEADER),
    ("AsyncClient.cpp", _CLIENTS_SOURCE),
    ("_custom_protocol.h", _SERVICES_HEADER),
    (".tcc", _SERVICES_HEADER),
    (".h", _SERVICES_HEADER),
    (".cpp", _SERVICES_SOURCE),
]

_TYPES_SUFFIX = "-types"
_CLIENTS_SUFFIX = "-clients"
_SERVICES_SUFFIX = "-services"

def _get_additional_compiler():
    return config.get_thrift2_compiler()

def _get_compiler():
    return config.get_thrift_compiler()

def _get_lang():
    return "cpp2"

def _get_names():
    return ("cpp2",)

def _get_compiler_lang():
    return "mstch_cpp2"

def _get_options(base_path, parsed_options):
    options = {
        "include_prefix": base_path,
    }
    options.update(parsed_options)
    return options

def _use_static_reflection(options):
    return "reflection" in options

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **_kwargs):
    _ignore = base_path
    _ignore = name

    thrift_base = paths.split_extension(
        paths.basename(src_and_dep_helpers.get_source_name(thrift_src)),
    )[0]

    genfiles = []

    gen_layouts = "frozen2" in options

    genfiles.append("%s_constants.h" % (thrift_base,))
    genfiles.append("%s_constants.cpp" % (thrift_base,))
    genfiles.append("%s_types.h" % (thrift_base,))
    genfiles.append("%s_types.cpp" % (thrift_base,))
    genfiles.append("%s_data.h" % (thrift_base,))
    genfiles.append("%s_data.cpp" % (thrift_base,))
    genfiles.append("%s_types_custom_protocol.h" % (thrift_base,))

    if gen_layouts:
        genfiles.append("%s_layouts.h" % (thrift_base,))
        genfiles.append("%s_layouts.cpp" % (thrift_base,))

    if _use_static_reflection(options):
        for suffix in _STATIC_REFLECTION_SUFFIXES:
            genfiles.append("%s_fatal%s.h" % (thrift_base, suffix))

    genfiles.append("%s_types.tcc" % (thrift_base,))

    for service in services:
        genfiles.append("%sAsyncClient.h" % (service,))
        genfiles.append("%sAsyncClient.cpp" % (service,))
        genfiles.append("%s.h" % (service,))
        genfiles.append("%s.cpp" % (service,))
        genfiles.append("%s_custom_protocol.h" % (service,))
        genfiles.append("%s.tcc" % (service,))

    # Everything is in the 'gen-cpp2' directory
    gen_paths = [paths.join("gen-cpp2", path) for path in genfiles]
    return {path: path for path in gen_paths}

def _get_src_type(src):
    for suffix, _type in _SUFFIXES:
        if src.endswith(suffix):
            return _type
    return None

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        cpp2_srcs = (),
        cpp2_headers = (),
        cpp2_deps = (),
        cpp2_external_deps = (),
        cpp2_compiler_flags = (),
        cpp2_compiler_specific_flags = None,
        visibility = None,
        **_kwargs):
    """
    Generates a handful of rules:
        <name>-<lang>-types: A library that just has the 'types' h, tcc and
                      cpp files
        <name>-<lang>-clients: A library that just has the client and async
                               client h and cpp files
        <name>-<lang>-services: A library that has h, tcc and cpp files
                                needed to run a specific service
        <name>-<lang>: An uber rule for compatibility that just depends on
                       the three above rules
    This is done in order to trim down dependencies and compilation units
    when clients/services are not actually needed.
    """

    _ignore = thrift_srcs

    sources = thrift_common.merge_sources_map(sources_map)

    types_sources = src_and_dep_helpers.convert_source_list(base_path, cpp2_srcs)
    types_headers = src_and_dep_helpers.convert_source_list(base_path, cpp2_headers)
    types_deps = [
        thrift_common.get_thrift_dep_target("folly", "indestructible"),
        thrift_common.get_thrift_dep_target("folly", "optional"),
    ]
    clients_sources = []
    clients_headers = []
    services_sources = []
    services_headers = []

    clients_deps = [
        thrift_common.get_thrift_dep_target("folly/futures", "core"),
        thrift_common.get_thrift_dep_target("folly/io", "iobuf"),
        ":%s%s" % (name, _TYPES_SUFFIX),
    ]
    services_deps = [
        # TODO: Remove this 'clients' dependency
        ":%s%s" % (name, _CLIENTS_SUFFIX),
        ":%s%s" % (name, _TYPES_SUFFIX),
    ]

    # Get sources/headers for the -types, -clients and -services rules
    for filename, file_target in sources.items():
        source_type = _get_src_type(filename)
        if source_type == _TYPES_SOURCE:
            types_sources.append(file_target)
        elif source_type == _TYPES_HEADER:
            types_headers.append(file_target)
        elif source_type == _CLIENTS_SOURCE:
            clients_sources.append(file_target)
        elif source_type == _CLIENTS_HEADER:
            clients_headers.append(file_target)
        elif source_type == _SERVICES_SOURCE:
            services_sources.append(file_target)
        elif source_type == _SERVICES_HEADER:
            services_headers.append(file_target)

    types_deps.extend([d + _TYPES_SUFFIX for d in deps])
    clients_deps.extend([d + _CLIENTS_SUFFIX for d in deps])
    services_deps.extend([d + _SERVICES_SUFFIX for d in deps])

    # Add in cpp-specific deps and external_deps
    common_deps = []
    common_deps.extend(cpp2_deps)
    common_external_deps = []
    common_external_deps.extend(cpp2_external_deps)

    # Add required dependencies for Stream support
    if "stream" in options:
        common_deps.append(
            thrift_common.get_thrift_dep_target("yarpl", "yarpl"),
        )
        clients_deps.append(
            thrift_common.get_thrift_dep_target(
                "thrift/lib/cpp2/transport/core",
                "thrift_client",
            ),
        )
        services_deps.append(
            thrift_common.get_thrift_dep_target(
                "thrift/lib/cpp2/transport/core",
                "thrift_processor",
            ),
        )

    # The 'json' thrift option will generate code that includes
    # headers from deprecated/json.  So add a dependency on it here
    # so all external header paths will also be added.
    if "json" in options:
        common_deps.append(
            thrift_common.get_thrift_dep_target("thrift/lib/cpp", "json_deps"),
        )
    if "frozen" in options:
        common_deps.append(thrift_common.get_thrift_dep_target(
            "thrift/lib/cpp",
            "frozen",
        ))
    if "frozen2" in options:
        common_deps.append(thrift_common.get_thrift_dep_target(
            "thrift/lib/cpp2/frozen",
            "frozen",
        ))

    # any c++ rule that generates thrift files must depend on the
    # thrift lib; add that dep now if it wasn't explicitly stated
    # already
    types_deps.append(
        thrift_common.get_thrift_dep_target("thrift/lib/cpp2", "types_deps"),
    )
    clients_deps.append(
        thrift_common.get_thrift_dep_target("thrift/lib/cpp2", "thrift_base"),
    )
    services_deps.append(
        thrift_common.get_thrift_dep_target("thrift/lib/cpp2", "thrift_base"),
    )
    if _use_static_reflection(options):
        common_deps.append(
            thrift_common.get_thrift_dep_target(
                "thrift/lib/cpp2/reflection",
                "reflection",
            ),
        )

    types_deps.extend(common_deps)
    services_deps.extend(common_deps)
    clients_deps.extend(common_deps)

    # Disable variable tracking for thrift generated C/C++ sources, as
    # it's pretty expensive and not necessarily useful (D2174972).
    common_compiler_flags = ["-fno-var-tracking"]
    common_compiler_flags.extend(cpp2_compiler_flags)

    common_compiler_specific_flags = (
        cpp2_compiler_specific_flags if cpp2_compiler_specific_flags else {}
    )

    # Support a global config for explicitly opting thrift generated C/C++
    # rules in to using modules.
    modular_headers = (
        read_bool(
            "cxx",
            "modular_headers_thrift_default",
            required = False,
        )
    )

    # Create the types, services and clients rules
    # Delegate to the C/C++ library converting to add in things like
    # sanitizer and BUILD_MODE flags.
    cpp_library(
        name = name + _TYPES_SUFFIX,
        srcs = types_sources,
        headers = types_headers,
        deps = types_deps,
        external_deps = common_external_deps,
        compiler_flags = common_compiler_flags,
        compiler_specific_flags = common_compiler_specific_flags,
        # TODO(T23121628): Some rules have undefined symbols (e.g. uncomment
        # and build //thrift/lib/cpp2/test:exceptservice-cpp2-types).
        undefined_symbols = True,
        visibility = visibility,
        modular_headers = modular_headers,
    )
    cpp_library(
        name = name + _CLIENTS_SUFFIX,
        srcs = clients_sources,
        headers = clients_headers,
        deps = clients_deps,
        external_deps = common_external_deps,
        compiler_flags = common_compiler_flags,
        compiler_specific_flags = common_compiler_specific_flags,
        # TODO(T23121628): Some rules have undefined symbols (e.g. uncomment
        # and build //thrift/lib/cpp2/test:Presult-cpp2-clients).
        undefined_symbols = True,
        visibility = visibility,
        modular_headers = modular_headers,
    )
    cpp_library(
        name + _SERVICES_SUFFIX,
        srcs = services_sources,
        headers = services_headers,
        deps = services_deps,
        external_deps = common_external_deps,
        compiler_flags = common_compiler_flags,
        compiler_specific_flags = common_compiler_specific_flags,
        visibility = visibility,
        modular_headers = modular_headers,
    )

    # Create a master rule that depends on -types, -services and -clients
    # for compatibility
    cpp_library(
        name,
        srcs = [],
        headers = [],
        deps = [
            ":" + name + _TYPES_SUFFIX,
            ":" + name + _CLIENTS_SUFFIX,
            ":" + name + _SERVICES_SUFFIX,
        ],
        visibility = visibility,
        modular_headers = modular_headers,
    )

cpp2_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_additional_compiler = _get_additional_compiler,
    get_compiler = _get_compiler,
    get_compiler_lang = _get_compiler_lang,
    get_options = _get_options,
    get_names = _get_names,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
