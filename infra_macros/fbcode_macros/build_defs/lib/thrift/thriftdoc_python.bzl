"""
Given a `thrift_library`:
 - Runs the `json_experimental` Thrift generator for each of its
   `.thrift` files.
 - Converts each of the resulting `.json` into a PAR-importable
   `thriftdoc_ast.py` file, while parsing the Thriftdoc validation DSL.
 - Packaged the ASTs into a `python_library` that can be used for Thrift
   struct validation.

Import this to get started with Thriftdoc validation:
    tupperware.thriftdoc.validator.validate_thriftdoc
Documentation is at:
    https://our.intern.facebook.com/intern/wiki/ThriftdocGuide

"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load(
    "@fbcode_macros//build_defs/lib:python_typing.bzl",
    "gen_typing_config",
    "get_typing_config_target",
)
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_AST_FILE = "thriftdoc_ast.py"
_GENERATOR_BINARY = "$(exe //tupperware/thriftdoc/validator:generate_thriftdoc_ast)"

def _get_lang():
    return "thriftdoc-py"

def _get_compiler_lang():
    return "json_experimental"

def _get_names():
    return ("thriftdoc-py",)

def _get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **_kwargs):
    _ignore = base_path
    _ignore = name
    _ignore = services
    _ignore = options

    # The Thrift compiler will make us a `gen-json_experimental`
    # directory per `.thrift` source file.  Use the input filename as
    # the keys to keep them from colliding in `merge_sources_map`.
    return {thrift_src: "gen-json_experimental"}

def _get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **_kwargs):
    _ignore = thrift_srcs
    _ignore = options
    source_suffix = "=gen-json_experimental"

    py_library_srcs = {}

    # `sources_map` has genrules that produce `json_experimental`
    # outputs.  This loop feeds their outputs into genrules that convert
    # each JSON into a PAR-includable `thriftdoc_ast.py` file, to be
    # collated into a `python_library` at the very end.
    for thrift_filename, json_experimental_rule in thrift_common.merge_sources_map(sources_map).items():
        # This genrule will end up writing its output here:
        #
        #   base_path/
        #     ThriftRule-thriftdoc-py-SourceFile.thrift=thriftdoc_ast.py/
        #       thriftdoc_ast.py
        #
        # The `=thriftdoc_ast.py` suffix is used to differentiate our
        # output from the Thrift-generated target named:
        #
        #   ThriftRuleName-thriftdoc-py-SourceFile.thrift
        #
        # In contrast to `gen_srcs`, nothing splits the rule name on `='.
        if not json_experimental_rule.endswith(source_suffix):
            fail("Expected {} to end with {}".format(json_experimental_rule, source_suffix))
        thriftdoc_rule = json_experimental_rule.replace(
            source_suffix,
            "=" + _AST_FILE,
        )

        if not thrift_filename.endswith(".thrift"):
            fail("Expected {} to end with .thrift".format(thrift_filename))

        # The output filename should be unique in our Python library's
        # linktree, and should be importable from Python.  The filename
        # below is a slight modification of the `.thrift` file's
        # original fbcode path, so it will be unique.  We could
        # guarantee a Python-safe path using `py_base_module` for the
        # base, but this does not seem worth it -- almost all paths in
        # fbcode are Python-safe.
        output_file = paths.join(
            base_path,
            thrift_filename[:-len(".thrift")],
            _AST_FILE,
        )
        if output_file in py_library_srcs:
            fail("Expected {} to be absent from {}".format(output_file, py_library_srcs))
        py_library_srcs[output_file] = thriftdoc_rule

        if not thriftdoc_rule.startswith(":"):
            fail("Expected {} to be a relative rule".format(thriftdoc_rule))
        fb_native.genrule(
            name = thriftdoc_rule[1:],  # Get rid of the initial ':',
            visibility = visibility,
            labels = ["generated"],
            out = _AST_FILE,
            srcs = [json_experimental_rule],
            cmd = " && ".join([
                # json_experimental gives us a single source file at the
                # moment.  Should that ever change, the JSON generator
                # will get an unknown positional arg, and fail loudly.
                _GENERATOR_BINARY + ' --format py > "$OUT" < "$SRCS"/*',
            ]),
        )
    if get_typing_config_target():
        gen_typing_config(name)
    fb_native.python_library(
        name = name,
        visibility = visibility,
        # tupperware.thriftdoc.validator.registry recursively loads this:
        base_module = "tupperware.thriftdoc.generated_asts",
        srcs = src_and_dep_helpers.convert_source_map(base_path, py_library_srcs),
        deps = deps,
    )

thriftdoc_python_thrift_converter = thrift_interface.make(
    get_lang = _get_lang,
    get_names = _get_names,
    get_compiler_lang = _get_compiler_lang,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
