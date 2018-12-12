"""
Specializer to support generating Python libraries from swig sources.
"""

load("@fbcode_macros//build_defs/lib/swig:lang_converter_info.bzl", "LangConverterInfo")
load(
    "@fbcode_macros//build_defs/lib:python_typing.bzl",
    "gen_typing_config",
    "get_typing_config_target",
)
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:cpp_python_extension.bzl", "cpp_python_extension")
load(
    "@fbsource//tools/build_defs:fb_native_wrapper.bzl",
    "fb_native",
)

def _get_lang():
    return "py"

def _get_lang_opt():
    return "-python"

def _get_lang_flags(java_package = None, **kwargs):
    _ignore = java_package
    _ignore = kwargs
    return [
        "-threads",
        "-safecstrings",
        "-classic",
    ]

def _get_generated_sources(module):
    src = module + ".py"
    return {src: src}

def _get_language_rule(
        base_path,
        name,
        module,
        hdr,
        src,
        gen_srcs,
        cpp_deps,
        deps,
        py_base_module = None,
        visibility = None,
        **kwargs):
    _ignore = base_path
    _ignore = hdr
    _ignore = kwargs

    # Build the C/C++ python extension from the generated C/C++ sources.
    cpp_python_extension(
        name = name + "-ext",
        srcs = [src],
        base_module = py_base_module,
        module_name = "_" + module,
        # Generated code uses a lot of shadowing, so disable GCC warnings
        # related to this.
        compiler_specific_flags = {
            "gcc": [
                "-Wno-shadow",
                "-Wno-shadow-local",
                "-Wno-shadow-compatible-local",
            ],
        },
        # This is pretty gross.  We format the deps just to get
        # re-parsed by the C/C++ converter.  Long-term, it'd be
        # be nice to support a better API in the converters to
        # handle higher-leverl objects, but for now we're stuck
        # doing this to re-use other converters.
        deps = src_and_dep_helpers.format_deps([d for d in cpp_deps if d.repo == None]),
        external_deps = [
            (d.repo, d.base_path, None, d.name)
            for d in cpp_deps
            if d.repo != None
        ],
    )

    # Generate the wrapping python library.
    out_deps = []
    out_deps.extend(deps)
    out_deps.append(":" + name + "-ext")

    attrs = {}
    attrs["name"] = name
    attrs["visibility"] = get_visibility(visibility, name)
    attrs["srcs"] = gen_srcs

    attrs["deps"] = out_deps
    if py_base_module != None:
        attrs["base_module"] = py_base_module

    # At some point swig targets should also include typing Options
    # For now we just need an empty directory.
    if get_typing_config_target():
        gen_typing_config(name)
    fb_native.python_library(**attrs)

    return []

python_converter = LangConverterInfo(
    get_lang = _get_lang,
    get_lang_opt = _get_lang_opt,
    get_lang_flags = _get_lang_flags,
    get_generated_sources = _get_generated_sources,
    get_language_rule = _get_language_rule,
)
