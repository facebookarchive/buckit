load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load(
    "@fbcode_macros//build_defs/config:read_configs.bzl",
    "read_boolean",
    "read_list",
)

def _enabled():
    enabled = read_boolean('cxx', 'modules', False)
    if enabled:
        compiler.require_global_compiler(
            "C/C++ modules are only supported when using clang globally",
            "clang")
    return enabled

def _get_module_name(cell, base_path, name):
    module_name = '_'.join([cell, base_path, name])

    # Sanitize input of chars that can't be used in a module map token.
    for c in '-/':
        module_name = module_name.replace(c, '_')

    return module_name

def _get_module_map(name, headers):
    lines = []
    lines.append('module {} {{'.format(name))
    for header, attrs in sorted(headers.items()):
        line = '  '
        for attr in sorted(attrs):
            line += attr + ' '
        line += 'header "{}"'.format(header)
        lines.append(line)
    lines.append('  export *')
    lines.append('}')
    return ''.join([line + '\n' for line in lines])

def _module_map_rule(name, module_name, headers):
    contents = _get_module_map(module_name, headers)
    native.genrule(
        name = name,
        out = 'module.modulemap',
        cmd = 'echo {} > "$OUT"'.format(shell.quote(contents)),
    )

def _get_implicit_module_deps():
    """
    A list of targets which should be implicitly added when building modules.
    Meant to be used for modules built for toolchain headers.
    """
    return read_list("fbcode", "implicit_module_deps", [], delimiter = ",")

def _gen_module(
        name,
        module_name,
        headers=None,
        header_dir=None,
        flags=(),
        platform_flags=(),
        deps=(),
        platform_deps=(),
        visibility=None):
    """
    Compile a module (i.e. `.pcm` file) from a `module.modulemap` file and the
    corresponding headers, specified as either a map or a directory.

    Arguments:
      name: The name of rule that builds the module.  This will also serve as
            a name prefix for any additional rules that need to be created.
      headers: A dictionary of headers to be compiled into a module, mapping
               their full include path to their sources.  Must contain a
               `module.modulemap` at the top-level.  Cannot be specified if
               `header_dir` is used.
      header_dir: A directory containing headers to be compiled into a module.
                  Must contain a `module.modulemap` at the top-level.  Cannot
                  be specified if `headers` is used.
      flags: Additional flags to pass to the compiler when building the module.
      platform_flags: Additional platform-specific flags, specified as a list
                      of regex and flag list tuples, to pass to the compiler
                      when building the module.
      deps: C/C++ deps providing headers used by the headers in this module.
      platform_deps: C/C++ platform-specific deps, specified as a list of regex
                     and flag list tuples, providing headers used by the
                     headers in this module.
    """

    # Must set exactly one of `headers` and `header_dir`.
    if ((headers == None and header_dir == None) or
            (headers != None and header_dir != None)):
        fail("must specify exactly on of `headers` or `headers_dir`")

    # Header dicts require a `module.modulemap` file at the root.
    if headers != None and headers.get("module.modulemap") == None:
        fail("`headers` must contain a top-level `module.modulemap` file")

    # A C/C++ library used to propagate C/C++ flags and deps to the
    # `cxx_genrule` below.
    helper_name = name + "-helper"
    native.cxx_library(
        name = helper_name,
        exported_preprocessor_flags = flags,
        exported_platform_preprocessor_flags = platform_flags,
        exported_deps = deps,
        exported_platform_deps = platform_deps,
        visibility = ["//{}:{}".format(native.package_name(), name)],
    )

    # Make headers, either from a directory or a map, available to the command
    # in a new "headers" directory.
    if headers != None:
        srcs = {paths.join("headers", h): s for h, s in headers.items()}
    else:
        srcs = {"headers": header_dir}

    native.cxx_genrule(
        name = name,
        out = module_name + ".pcm",
        srcs = srcs,
        # TODO(T32246672): Clang currently embeds absolute paths into PCM
        # files, and we're not sure how to avoid this.  Until we do, mark
        # module compilation as uncacheable.
        cacheable = False,
        cmd = "\n".join(
            [# TODO(T32246582): This is gross, but we currently need to run the
             # C/C++ compilers from the root of fbcode, so search up the dir
             # tree to find it.
             "while test ! -r .buckconfig -a `pwd` != / ; do cd ..; done",

             # Set up the args for module compilation.
             "args=()",
             "args+=($(cxx))",

             # Add toolchain flags
             "args+=($(cxxppflags :{}))".format(helper_name),
             "args+=($(cxxflags))",

             # Enable building *.pcm module files.
             'args+=("-Xclang" "-emit-module")',
             # Set the name of the module we're building.
             'args+=("-fmodule-name="{})'.format(shell.quote(module_name)),
             # The inputs to module compilation are C++ headers.
             'args+=("-x" "c++-header")',

             'args+=("-o" "$OUT")',

             # Setup the headers as inputs to the compilation by adding the
             # header dir implicitly via an `-I...` flag (for implicit searches
             # for headers specified in the module map) and the
             # `module.modulemap` as the main input arg.
             'args+=("-I$SRCDIR/headers")',
             'args+=("$SRCDIR/headers/module.modulemap")',

             'exec "${args[@]}"']),
        visibility = visibility,
    )

modules = struct(
    enabled = _enabled,
    gen_module = _gen_module,
    get_implicit_module_deps = _get_implicit_module_deps,
    get_module_map = _get_module_map,
    get_module_name = _get_module_name,
    module_map_rule = _module_map_rule,
)
