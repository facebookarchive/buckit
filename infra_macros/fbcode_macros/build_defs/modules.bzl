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

# Flags to apply to compilations to enabled modules.
_TOOLCHAIN_FLAGS = [
    # Enable modules.
    "-fmodules",
    # Show what modules are built during compilation.
    "-Rmodule-build",
    # Explicitly enable implicit module maps.  This is needed to allow for
    # automatic translation from `#include ...` lines to the required module
    # import via searching for `module.modulemap`s when using manual modules
    # specified on the command-line via `-fmodule-file=...`.
    "-fimplicit-module-maps",
    # Normally, clang would auto-load it's builtin module map file,
    # but since we're explicitly managing the module deps, it's
    # unnecessary, so disable it so there's less magic going on.
    "-fno-builtin-module-map",
    # Don't implicitly build modules, and require all needed modules
    # to be explicitly added via `-fmodule-file=...`.
    "-fno-implicit-modules",
    # We shouldn't be using the builtin clang modules cache since
    # we're not using implicit modules, but set it to a non-existent
    # path to make sure (this is the location where clang would place
    # implicitly built modules).
    "-fmodules-cache-path=/DOES/NOT/EXIST",
    # Prevent using global modules index, as this would exist outside
    # Buck's caching (NOTE(agallagher): I *think* this is just used
    # for improving error messages, but I'm not sure).
    "-Xclang",
    "-fno-modules-global-index",
    # Warn about using non-module includes inside modules.  This effectively
    # means tp2 projects w/o `module.modulemap` files cannot be used (but also
    # helps prevent duplicate definition issues where multiple fbcode modules
    # pull in the same tp2 header textually).
    "-Wnon-modular-include-in-module",

    # NOTE(agallagher): Some additional flags which are likely useful
    # for determinism, but which I'm not entirely sure how yet:
    #  -fmodules-user-build-path <directory>
    #  -Xclang -fdisable-module-hash
    #  -Xclang -fmodules-user-build-path -Xclang <directory>
]

def _get_toolchain_flags():
    return _TOOLCHAIN_FLAGS

def _get_deprecated_auto_module_names():
    """
    Return projects (specified via `<cell>//<project>`) that use old-style
    sanitized module names.
    """

    projs = read_list("fbcode", "old_style_module_names", [], delimiter = ",")
    return [tuple(proj.split("//")) for proj in projs]

def _sanitize_name(name):
    """
    Sanitize input of chars that can't be used in a module map token.
    """

    for c in '-/.':
        name = name.replace(c, '_')

    return name

def _get_module_name(cell, base_path, name):
    """
    Return a module name to use for the given cell, base path, and name tuple.
    """

    if (cell, base_path) in _get_deprecated_auto_module_names():
        return _sanitize_name('_'.join([cell, base_path, name]))
    return '{}//{}:{}'.format(cell, base_path, name)

def _get_module_map(name, headers):
    lines = []
    lines.append('module "{}" {{'.format(name))
    for header, attrs in sorted(headers.items()):
        lines.append('  module "{}" {{'.format(header))
        header_line = '    '
        for attr in sorted(attrs):
            header_line += attr + ' '
        header_line += 'header "{}"'.format(header)
        lines.append(header_line)
        lines.append('    export *')
        lines.append('  }')
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

    Args:
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
        out = "module.pcm",
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
             "args+=({})".format(' '.join(map(shell.quote, _get_toolchain_flags()))),

             # Enable building *.pcm module files.
             'args+=("-Xclang" "-emit-module")',
             # Set the name of the module we're building.
             'args+=("-fmodule-name="{})'.format(shell.quote(module_name)),
             # The inputs to module compilation are C++ headers.
             'args+=("-x" "c++-header")',

             # Setup the headers as inputs to the compilation by adding the
             # header dir implicitly via an `-I...` flag (for implicit searches
             # for headers specified in the module map) and the
             # `module.modulemap` as the main input arg.
             'args+=("-I$SRCDIR/headers")',
             'args+=("$SRCDIR/headers/module.modulemap")',

             # Output via "-" and redirect to the output file rather than going
             # directly to the output file.  This makes clang avoid embedding
             # an absolute path for it's "original pch dir" attribute.
             'args+=("-o" "-")',

             # NOTE(T32246672): Clang will embed paths as specified on the
             # command-line so, to avoid baking in absolute paths, sanitize
             # them here.
             'for i in "${!args[@]}"; do',
             '  args[$i]=${args[$i]//$PWD\//}',
             'done',

             'exec "${args[@]}" > "$OUT"']),
        visibility = visibility,
    )

modules = struct(
    enabled = _enabled,
    gen_module = _gen_module,
    get_implicit_module_deps = _get_implicit_module_deps,
    get_module_map = _get_module_map,
    get_module_name = _get_module_name,
    get_toolchain_flags = _get_toolchain_flags,
    module_map_rule = _module_map_rule,
)
