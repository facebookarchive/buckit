"""
"""

load("@bazel_skylib//lib:collections.bzl", "collections")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib/thrift:thrift_interface.bzl", "thrift_interface")
load(
    "@fbcode_macros//build_defs/lib:python_typing.bzl",
    "gen_typing_config",
    "get_typing_config_target",
)
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:thrift_common.bzl", "thrift_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_NORMAL = "normal"
_TWISTED = "twisted"
_ASYNCIO = "asyncio"
_PYI = "pyi"
_PYI_ASYNCIO = "pyi-asyncio"

_NORMAL_EXT = ".py"
_TWISTED_EXT = ".py"
_ASYNCIO_EXT = ".py"
_PYI_EXT = ".pyi"
_PYI_ASYNCIO_EXT = ".pyi"

_THRIFT_PY_LIB_RULE_NAME = target_utils.RootRuleTarget("thrift/lib/py", "py")
_THRIFT_PY_TWISTED_LIB_RULE_NAME = target_utils.RootRuleTarget("thrift/lib/py", "twisted")
_THRIFT_PY_ASYNCIO_LIB_RULE_NAME = target_utils.RootRuleTarget("thrift/lib/py", "asyncio")

_POSTPROCESS_MSG_NO_BASE_MODULE = """
Compiling {src} did not generate source in {ttypes_path}
Does the "\\"namespace {py_flavor}\\"" directive in the thrift file match the base_module specified in the TARGETS file?
  base_module not specified, assumed to be "\\"{base_module}\\""
  thrift file should contain "\\"namespace {py_flavor} {expected_ns}\\""
""".strip()

_POSTPROCESS_MSG_WITH_BASE_MODULE = """
Compiling {src} did not generate source in {ttypes_path}
Does the "\\"namespace {py_flavor}\\"" directive in the thrift file match the base_module specified in the TARGETS file?
  base_module is "\\"{base_module}\\""
  thrift file should contain "\\"namespace {py_flavor} {expected_ns}\\""
""".strip()

def _get_name(flavor, prefix, sep, base_module = False):
    if flavor in (_PYI, _PYI_ASYNCIO):
        if not base_module:
            return flavor
        elif flavor == _PYI_ASYNCIO:
            flavor = _ASYNCIO
        else:
            flavor = _NORMAL

    if flavor in (_TWISTED, _ASYNCIO):
        prefix += sep + flavor
    return prefix

def _get_thrift_base(thrift_src):
    return paths.split_extension(paths.basename(thrift_src))[0]

def _get_base_module(flavor, **kwargs):
    """
    Get the user-specified base-module set in via the parameter in the
    `thrift_library()`.
    """

    base_module = kwargs.get(
        _get_name(flavor, "py", "_", base_module = True) + "_base_module",
    )

    # If no asyncio/twisted specific base module parameter is present,
    # fallback to using the general `py_base_module` parameter.
    if base_module == None:
        base_module = kwargs.get("py_base_module")

    # If nothing is set, just return `None`.
    if base_module == None:
        return None

    # Otherwise, since we accept pathy base modules, normalize it to look
    # like a proper module.
    return "/".join(base_module.split("."))

def _get_thrift_dir(base_path, thrift_src, flavor, **kwargs):
    thrift_base = _get_thrift_base(thrift_src)
    base_module = _get_base_module(flavor, **kwargs)
    if base_module == None:
        base_module = base_path
    return paths.join(base_module, thrift_base)

def _add_ext(path, ext):
    if not path.endswith(ext):
        path += ext
    return path

def _get_pyi_dependency(name, flavor):
    if name.endswith("-asyncio"):
        name = name[:-len("-asyncio")]
    if name.endswith("-py"):
        name = name[:-len("-py")]
    if flavor == _ASYNCIO:
        return name + "-pyi-asyncio"
    else:
        return name + "-pyi"

def _get_names(flavor):
    return collections.uniq([
        _get_name(flavor, "py", "-"),
        _get_name(flavor, "python", "-"),
    ])

def _normal_get_names():
    return _get_names(_NORMAL)

def _twisted_get_names():
    return _get_names(_TWISTED)

def _asyncio_get_names():
    return _get_names(_ASYNCIO)

def _pyi_get_names():
    return _get_names(_PYI)

def _pyi_asyncio_get_names():
    return _get_names(_PYI_ASYNCIO)

def _normal_get_lang():
    return _get_name(_NORMAL, "py", "-")

def _twisted_get_lang():
    return _get_name(_TWISTED, "py", "-")

def _asyncio_get_lang():
    return _get_name(_ASYNCIO, "py", "-")

def _pyi_get_lang():
    return _get_name(_PYI, "py", "-")

def _pyi_asyncio_get_lang():
    return _get_name(_PYI_ASYNCIO, "py", "-")

def _normal_get_compiler_lang():
    return "py"

def _twisted_get_compiler_lang():
    return "py"

def _asyncio_get_compiler_lang():
    return "py"

def _pyi_get_compiler_lang():
    return "mstch_pyi"

def _pyi_asyncio_get_compiler_lang():
    return "mstch_pyi"

def _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        flavor,
        ext,
        **kwargs):
    # The location of the generated thrift files depends on the value of
    # the "namespace py" directive in the .thrift file, and we
    # unfortunately don't know what this value is.  After compilation, make
    # sure the ttypes.py file exists in the location we expect.  If not,
    # there is probably a mismatch between the base_module parameter in the
    # TARGETS file and the "namespace py" directive in the .thrift file.
    thrift_base = _get_thrift_base(thrift_src)
    thrift_dir = _get_thrift_dir(base_path, thrift_src, flavor, **kwargs)

    output_dir = paths.join(out_dir, "gen-py", thrift_dir)
    ttypes_path = paths.join(output_dir, "ttypes" + ext)

    if flavor == _ASYNCIO or flavor == _PYI_ASYNCIO:
        py_flavor = "py.asyncio"
    elif flavor == _TWISTED:
        py_flavor = "py.twisted"
    else:
        py_flavor = "py"

    base_module = _get_base_module(flavor = flavor, **kwargs)
    if base_module == None:
        base_module = base_path
        msg_template = _POSTPROCESS_MSG_NO_BASE_MODULE
    else:
        msg_template = _POSTPROCESS_MSG_WITH_BASE_MODULE

    expected_ns = [p for p in base_module.split("/") if p]
    expected_ns.append(thrift_base)
    expected_ns = ".".join(expected_ns)

    msg = msg_template.format(
        src = paths.join(base_path, thrift_src),
        ttypes_path = ttypes_path,
        py_flavor = py_flavor,
        base_module = base_module,
        expected_ns = expected_ns,
    )

    cmd = "if [ ! -f %s ]; then " % (ttypes_path,)
    for line in msg.splitlines():
        cmd += ' echo "%s" >&2;' % (line,)
    cmd += " false; fi"

    return cmd

def _normal_get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        **kwargs):
    return _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        _NORMAL,
        _NORMAL_EXT,
        **kwargs
    )

def _twisted_get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        **kwargs):
    return _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        _TWISTED,
        _TWISTED_EXT,
        **kwargs
    )

def _asyncio_get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        **kwargs):
    return _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        _ASYNCIO,
        _ASYNCIO_EXT,
        **kwargs
    )

def _pyi_get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        **kwargs):
    return _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        _PYI,
        _PYI_EXT,
        **kwargs
    )

def _pyi_asyncio_get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        **kwargs):
    return _get_postprocess_command(
        base_path,
        thrift_src,
        out_dir,
        _PYI_ASYNCIO,
        _PYI_ASYNCIO_EXT,
        **kwargs
    )

def _get_options(parsed_options, flavor):
    options = {}

    # We always use new style for non-python3.
    if "new_style" in parsed_options:
        fail('the "new_style" thrift python option is redundant')

    # Add flavor-specific option.
    if flavor == _TWISTED:
        options["twisted"] = None
    elif flavor in (_ASYNCIO, _PYI_ASYNCIO):
        options["asyncio"] = None

    # Always use "new_style" classes.
    options["new_style"] = None

    options.update(parsed_options)

    return options

def _normal_get_options(base_path, parsed_options):
    _ignore = base_path
    return _get_options(parsed_options, _NORMAL)

def _twisted_get_options(base_path, parsed_options):
    _ignore = base_path
    return _get_options(parsed_options, _TWISTED)

def _asyncio_get_options(base_path, parsed_options):
    _ignore = base_path
    return _get_options(parsed_options, _ASYNCIO)

def _pyi_get_options(base_path, parsed_options):
    _ignore = base_path
    return _get_options(parsed_options, _PYI)

def _pyi_asyncio_get_options(base_path, parsed_options):
    _ignore = base_path
    return _get_options(parsed_options, _PYI_ASYNCIO)

def _get_generated_sources(
        base_path,
        thrift_src,
        services,
        flavor,
        ext,
        **kwargs):
    thrift_base = _get_thrift_base(thrift_src)
    thrift_dir = _get_thrift_dir(base_path, thrift_src, flavor, **kwargs)

    genfiles = []

    genfiles.append("constants" + ext)
    genfiles.append("ttypes" + ext)

    for service in services:
        # "<service>.py" and "<service>-remote" are generated for each
        # service
        genfiles.append(service + ext)
        if flavor == _NORMAL:
            genfiles.append(service + "-remote")

    return {
        _add_ext(paths.join(thrift_base, path), ext): paths.join("gen-py", thrift_dir, path)
        for path in genfiles
    }

def _normal_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **kwargs):
    _ignore = name
    _ignore = options
    return _get_generated_sources(
        base_path,
        thrift_src,
        services,
        _NORMAL,
        _NORMAL_EXT,
        **kwargs
    )

def _twisted_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **kwargs):
    _ignore = name
    _ignore = options
    return _get_generated_sources(
        base_path,
        thrift_src,
        services,
        _TWISTED,
        _TWISTED_EXT,
        **kwargs
    )

def _asyncio_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **kwargs):
    _ignore = name
    _ignore = options
    return _get_generated_sources(
        base_path,
        thrift_src,
        services,
        _ASYNCIO,
        _ASYNCIO_EXT,
        **kwargs
    )

def _pyi_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **kwargs):
    _ignore = name
    _ignore = options
    return _get_generated_sources(
        base_path,
        thrift_src,
        services,
        _PYI,
        _PYI_EXT,
        **kwargs
    )

def _pyi_asyncio_get_generated_sources(
        base_path,
        name,
        thrift_src,
        services,
        options,
        **kwargs):
    _ignore = name
    _ignore = options
    return _get_generated_sources(
        base_path,
        thrift_src,
        services,
        _PYI_ASYNCIO,
        _PYI_ASYNCIO_EXT,
        **kwargs
    )

def _get_language_rule(
        base_path,
        name,
        options,
        sources_map,
        deps,
        visibility,
        flavor,
        **kwargs):
    srcs = thrift_common.merge_sources_map(sources_map)
    base_module = _get_base_module(flavor, **kwargs)

    out_deps = []
    out_deps.extend(deps)

    # If this rule builds thrift files, automatically add a dependency
    # on the python thrift library.
    out_deps.append(target_utils.target_to_label(_THRIFT_PY_LIB_RULE_NAME))

    # If thrift files are build with twisted support, add also
    # dependency on the thrift's twisted transport library.
    if flavor == _TWISTED or "twisted" in options:
        out_deps.append(
            target_utils.target_to_label(_THRIFT_PY_TWISTED_LIB_RULE_NAME),
        )

    # If thrift files are build with asyncio support, add also
    # dependency on the thrift's asyncio transport library.
    if flavor == _ASYNCIO or "asyncio" in options:
        out_deps.append(
            target_utils.target_to_label(_THRIFT_PY_ASYNCIO_LIB_RULE_NAME),
        )

    if flavor in (_NORMAL, _ASYNCIO):
        out_deps.append(":" + _get_pyi_dependency(name, flavor))
        has_types = True
    else:
        has_types = False

    if get_typing_config_target():
        if has_types:
            gen_typing_config(
                name,
                base_module if base_module != None else base_path,
                srcs.keys(),
                out_deps,
                typing = True,
                visibility = visibility,
            )
        else:
            gen_typing_config(name)

    fb_native.python_library(
        name = name,
        visibility = visibility,
        srcs = srcs,
        base_module = base_module,
        deps = out_deps,
    )

def _normal_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **kwargs):
    _ignore = thrift_srcs
    return _get_language_rule(
        base_path,
        name,
        options,
        sources_map,
        deps,
        visibility,
        _NORMAL,
        **kwargs
    )

def _twisted_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **kwargs):
    _ignore = thrift_srcs
    return _get_language_rule(
        base_path,
        name,
        options,
        sources_map,
        deps,
        visibility,
        _TWISTED,
        **kwargs
    )

def _asyncio_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **kwargs):
    _ignore = thrift_srcs
    return _get_language_rule(
        base_path,
        name,
        options,
        sources_map,
        deps,
        visibility,
        _ASYNCIO,
        **kwargs
    )

def _pyi_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **kwargs):
    _ignore = thrift_srcs
    return _get_language_rule(
        base_path,
        name,
        options,
        sources_map,
        deps,
        visibility,
        _PYI,
        **kwargs
    )

def _pyi_asyncio_get_language_rule(
        base_path,
        name,
        thrift_srcs,
        options,
        sources_map,
        deps,
        visibility,
        **kwargs):
    _ignore = thrift_srcs
    return _get_language_rule(
        base_path,
        name,
        options,
        sources_map,
        deps,
        visibility,
        _PYI_ASYNCIO,
        **kwargs
    )

python_normal_thrift_converter = thrift_interface.make(
    get_lang = _normal_get_lang,
    get_names = _normal_get_names,
    get_compiler_lang = _normal_get_compiler_lang,
    get_generated_sources = _normal_get_generated_sources,
    get_language_rule = _normal_get_language_rule,
    get_options = _normal_get_options,
    get_postprocess_command = _normal_get_postprocess_command,
)

python_twisted_thrift_converter = thrift_interface.make(
    get_lang = _twisted_get_lang,
    get_names = _twisted_get_names,
    get_compiler_lang = _twisted_get_compiler_lang,
    get_generated_sources = _twisted_get_generated_sources,
    get_language_rule = _twisted_get_language_rule,
    get_options = _twisted_get_options,
    get_postprocess_command = _twisted_get_postprocess_command,
)

python_asyncio_thrift_converter = thrift_interface.make(
    get_lang = _asyncio_get_lang,
    get_names = _asyncio_get_names,
    get_compiler_lang = _asyncio_get_compiler_lang,
    get_generated_sources = _asyncio_get_generated_sources,
    get_language_rule = _asyncio_get_language_rule,
    get_options = _asyncio_get_options,
    get_postprocess_command = _asyncio_get_postprocess_command,
)

python_pyi_thrift_converter = thrift_interface.make(
    get_lang = _pyi_get_lang,
    get_names = _pyi_get_names,
    get_compiler_lang = _pyi_get_compiler_lang,
    get_generated_sources = _pyi_get_generated_sources,
    get_language_rule = _pyi_get_language_rule,
    get_options = _pyi_get_options,
    get_postprocess_command = _pyi_get_postprocess_command,
)

python_pyi_asyncio_thrift_converter = thrift_interface.make(
    get_lang = _pyi_asyncio_get_lang,
    get_names = _pyi_asyncio_get_names,
    get_compiler_lang = _pyi_asyncio_get_compiler_lang,
    get_generated_sources = _pyi_asyncio_get_generated_sources,
    get_language_rule = _pyi_asyncio_get_language_rule,
    get_options = _pyi_asyncio_get_options,
    get_postprocess_command = _pyi_asyncio_get_postprocess_command,
)
