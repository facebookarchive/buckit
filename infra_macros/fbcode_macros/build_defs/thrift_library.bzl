load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:cpp2.bzl", "cpp2_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:d.bzl", "d_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:go.bzl", "go_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:haskell.bzl", "haskell_deprecated_thrift_converter", "haskell_hs2_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:java.bzl", "java_deprecated_apache_thrift_converter", "java_deprecated_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:js.bzl", "js_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:ocaml.bzl", "ocaml_thrift_converter")
load(
    "@fbcode_macros//build_defs/lib/thrift:python.bzl",
    "python_asyncio_thrift_converter",
    "python_normal_thrift_converter",
    "python_pyi_asyncio_thrift_converter",
    "python_pyi_thrift_converter",
    "python_twisted_thrift_converter",
)
load("@fbcode_macros//build_defs/lib/thrift:python3.bzl", "python3_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:rust.bzl", "rust_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:swift.bzl", "swift_thrift_converter")
load("@fbcode_macros//build_defs/lib/thrift:thriftdoc_python.bzl", "thriftdoc_python_thrift_converter")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_list", "is_string", "is_tuple")

_PY_REMOTES_EXTERNAL_DEPS = (
    "python-future",
    "six",
)

def _instantiate_converters():
    all_converters = [
        cpp2_thrift_converter,
        d_thrift_converter,
        go_thrift_converter,
        haskell_deprecated_thrift_converter,
        haskell_hs2_thrift_converter,
        js_thrift_converter,
        ocaml_thrift_converter,
        rust_thrift_converter,
        thriftdoc_python_thrift_converter,
        python3_thrift_converter,
        python_normal_thrift_converter,
        python_twisted_thrift_converter,
        python_asyncio_thrift_converter,
        python_pyi_thrift_converter,
        python_pyi_asyncio_thrift_converter,
        java_deprecated_thrift_converter,
        java_deprecated_apache_thrift_converter,
        swift_thrift_converter,
    ]
    converters = {}
    name_to_lang = {}
    for converter in all_converters:
        converters[converter.get_lang()] = converter
        for name in converter.get_names():
            name_to_lang[name] = converter.get_lang()

    return converters, name_to_lang

# TODO: Make private
CONVERTERS, NAMES_TO_LANG = _instantiate_converters()

def filter_language_specific_kwargs(**kwargs):
    """
    Filter out kwargs that aren't actually present

    We want to define all of our possible arguments up front for discoverability by
    users, however some converters would like to specify their own defaults for
    various functions if the kwarg wasn't provided. (e.g. cpp2_srcs, or
    javadeprecated_maven_publisher_version_prefix. So, filter out any of the kwargs
    that are == None (unspecified), and rely on rules to specify their own defaults.
    """

    return {k: v for k, v in kwargs.items() if v != None}

def get_exported_include_tree(dep):
    """
    Generate the exported thrift source includes target use for the given
    thrift library target.
    """
    return dep + "-thrift-includes"

# TODO: Make private
# TODO: Remove the need for this by making this a list everywhere
def parse_thrift_args(args):
    """
    For some reason we accept `thrift_args` as either a list or
    space-separated string.
    """

    if is_string(args):
        args = args.split()

    return args

# TODO: Make private
def fixup_thrift_srcs(srcs):
    """ Normalize the format of the thrift_srcs attribute """
    new_srcs = {}
    for name, services in sorted(srcs.items()):
        if services == None:
            services = []
        elif not is_tuple(services) and not is_list(services):
            services = [services]
        new_srcs[name] = services
    return new_srcs

# TODO: Make private
def parse_thrift_options(options):
    """
    Parse the option list or string into a dict.
    """

    parsed = {}

    if is_string(options):
        options = options.split(",")

    for option in options:
        if "=" in option:
            option, val = option.rsplit("=", 1)
            parsed[option] = val
        else:
            parsed[option] = None

    return parsed

# TODO: Make private
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
