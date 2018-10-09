load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load(
    "@fbcode_macros//build_defs/config:read_configs.bzl",
    "read_boolean",
    "read_list",
)

def _enabled():
    enabled = read_boolean("cxx", "modules", False)
    if enabled:
        compiler.require_global_compiler(
            "C/C++ modules are only supported when using clang globally",
            "clang",
        )
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
    # Don't store the module directory path as an absolute path, as this is
    # different depending on repo location.
    "-Xclang",
    "-fno-absolute-module-directory",

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

    for c in "-/.":
        name = name.replace(c, "_")

    return name

def _get_module_name(cell, base_path, name):
    """
    Return a module name to use for the given cell, base path, and name tuple.
    """

    if (cell, base_path) in _get_deprecated_auto_module_names():
        return _sanitize_name("_".join([cell, base_path, name]))
    return "{}//{}:{}".format(cell, base_path, name)

def _get_module_map(name, headers):
    lines = []
    lines.append('module "{}" {{'.format(name))
    for header, attrs in sorted(headers.items()):
        lines.append('  module "{}" {{'.format(header))
        header_line = "    "
        for attr in sorted(attrs):
            header_line += attr + " "
        header_line += 'header "{}"'.format(header)
        lines.append(header_line)
        lines.append("    export *")
        lines.append("  }")
    lines.append("}")
    return "".join([line + "\n" for line in lines])

def _module_map_rule(name, module_name, headers):
    contents = _get_module_map(module_name, headers)
    native.genrule(
        name = name,
        out = "module.modulemap",
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
        headers = None,
        header_dir = None,
        header_prefix = "",
        flags = (),
        platform_flags = (),
        deps = (),
        platform_deps = (),
        override_module_home = None,
        visibility = None):
    """
    Compile a module (i.e. `.pcm` file) from a `module.modulemap` file and the
    corresponding headers, specified as either a map or a directory.

    Args:
      name: The name of rule that builds the module.  This will also serve as
            a name prefix for any additional rules that need to be created.
      module_name: The name of the module at the C++ level
      headers: A dictionary of headers to be compiled into a module, mapping
               their full include path to their sources.  Must contain a
               `module.modulemap` at the top-level.  Cannot be specified if
               `header_dir` is used.
      header_dir: A directory containing headers to be compiled into a module.
                  Must contain a `module.modulemap` at the top-level.  Cannot
                  be specified if `headers` is used.
      header_prefix: A path component that the headers are actually relative to.
                     This path will be used to prefix the header files in error
                     messages from compiler errors seen when building this
                     module.
      flags: Additional flags to pass to the compiler when building the module.
      platform_flags: Additional platform-specific flags, specified as a list
                      of regex and flag list tuples, to pass to the compiler
                      when building the module.
      override_module_home: Postprocess the module and replace the module home
                            built into the modue with the given one.
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
        srcs = {paths.join("module_headers", h): s for h, s in headers.items()}
    else:
        srcs = {"module_headers": header_dir}

    commands = [
        "set -euo pipefail",

        # TODO(T32246582): This is gross, but we currently need to run the
        # C/C++ compilers from the root of fbcode, so search up the dir
        # tree to find it.
        "while test ! -r .buckconfig -a `pwd` != / ; do cd ..; done",

        # Set up the args for module compilation.
        "args=()",
        "args+=($(cxx))",

        # Add toolchain flags
        "args+=($(cxxppflags :{}))".format(helper_name),
        "args+=($(cxxflags))",
        "args+=({})".format(" ".join([shell.quote(f) for f in _get_toolchain_flags()])),

        # Enable building *.pcm module files.
        'args+=("-Xclang" "-emit-module")',
        # Set the name of the module we're building.
        'args+=("-fmodule-name="{})'.format(shell.quote(module_name)),
        # The inputs to module compilation are C++ headers.
        'args+=("-x" "c++-header")',
        'args+=("-Xclang" "-fno-validate-pch")',

        # Setup the headers as inputs to the compilation by adding the
        # header dir implicitly via an `-I...` flag (for implicit searches
        # for headers specified in the module map) and the
        # `module.modulemap` as the main input arg.
        'args+=("-I$SRCDIR/module_headers")',
        'args+=("$SRCDIR/module_headers/module.modulemap")',

        # Output via "-" and redirect to the output file rather than going
        # directly to the output file.  This makes clang avoid embedding
        # an absolute path for it's "original pch dir" attribute.
        'args+=("-o" "-")',

        # NOTE(T32246672): Clang will embed paths as specified on the
        # command-line so, to avoid baking in absolute paths, sanitize
        # them here.
        'for i in "${!args[@]}"; do',
        "  args[$i]=${args[$i]//$PWD\//}",
        "done",
        ('("${{args[@]}}" 3>&1 1>&2 2>&3 3>&-) 2>"$OUT"' +
         ' | >&2 sed "s|${{SRCDIR//$PWD\//}}/module_headers/|{}|g"')
            .format(header_prefix),
    ]

    # Postprocess the built module and update it with the new module home.
    if override_module_home != None:
        commands.extend([
            'OLD="${SRCDIR//$PWD\//}"/module_headers',
            'VER="\$(echo "$OLD" | grep -Po ",v[a-f0-9]{7}(?=__srcs/)"; true)"',
            'NEW="\$(printf {} "$VER")"'
            .format(shell.quote(override_module_home)),
            # We do in in-place update, which requires that the new and old
            # module homes are identical in length.  To meet this requirement,
            # assume that the length of the new module home is either already
            # the same length or smaller, padding with `/` when necessary.
            "if [ ${#NEW} -gt ${#OLD} ]; then",
            '  >&2 echo "New module home ($NEW) bigger than old one ($OLD)"',
            "  exit 1",
            "fi",
            'NEW="\\$(echo -n "$NEW" | sed -e :a -e' +
            ' "s|^.\{1,$(expr "$(echo -n "$OLD" | wc -c)" - 1)\}$|&/|;ta")"',
            'sed -i "s|$OLD|$NEW|g" "$OUT"',
        ])

    native.cxx_genrule(
        name = name,
        out = "module.pcm",
        srcs = srcs,
        cmd = "\n".join(commands),
        visibility = visibility,
    )

def _gen_tp2_cpp_module(
        name,
        module_name,
        platform,
        header_dir = None,
        headers = None,
        flags = (),
        dependencies = (),
        local_submodule_visibility = False,
        visibility = None):
    """
    A thin wrapper around `modules.gen_module()`, which performs some deps
    formatting and adds fbcode build flags (e.g. from BUILD_MODE)

    Args:
      name: The name of rule that builds the module.  This will also serve as
            a name prefix for any additional rules that need to be created.
      module_name: The name of the module at the C++ level
      headers: A dictionary of headers to be compiled into a module, mapping
               their full include path to their sources.  Must contain a
               `module.modulemap` at the top-level.  Cannot be specified if
               `header_dir` is used.
      header_dir: A directory containing headers to be compiled into a module.
                  Must contain a `module.modulemap` at the top-level.  Cannot
                  be specified if `headers` is used.
      flags: Additional flags to pass to the compiler when building the module.
      deps: C/C++ deps providing headers used by the headers in this module.
      local_submodule_visibility: Whether or not modules-local-submodule-visibility
                                  should be added to the cxxpp flags used by
                                  gen_module()
    """

    base_path = native.package_name()
    if not third_party.is_tp2(base_path):
        fail("gen_tp2_cpp_module can only be called within a tp2 package, not " + base_path)

    # Setup flags.
    out_flags = []
    if local_submodule_visibility:
        out_flags.extend(["-Xclang", "-fmodules-local-submodule-visibility"])
    out_flags.extend(flags)
    out_flags.extend(cpp_flags.get_extra_cxxppflags())

    # Form platform-specific flags.
    out_platform_flags = []
    out_platform_flags.extend(
        cpp_flags.get_compiler_flags(base_path)["cxx_cpp_output"],
    )

    # Convert deps to lower-level Buck deps/platform-deps pair.
    out_deps, out_platform_deps = (
        src_and_dep_helpers.format_all_deps(
            dependencies,
            platform = platform,
        )
    )

    # Generate the module file.
    _gen_module(
        name = name,
        headers = headers,
        flags = out_flags,
        header_dir = header_dir,
        header_prefix = paths.join(base_path, header_dir) + "/",
        module_name = module_name,
        platform_deps = out_platform_deps,
        platform_flags = out_platform_flags,
        visibility = visibility,
        deps = out_deps,
    )

modules = struct(
    enabled = _enabled,
    gen_module = _gen_module,
    gen_tp2_cpp_module = _gen_tp2_cpp_module,
    get_implicit_module_deps = _get_implicit_module_deps,
    get_module_map = _get_module_map,
    get_module_name = _get_module_name,
    get_toolchain_flags = _get_toolchain_flags,
    module_map_rule = _module_map_rule,
)
