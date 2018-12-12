load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:cpp_flags.bzl", "cpp_flags")
load("@fbcode_macros//build_defs/lib:lua_common.bzl", "lua_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:lua_library.bzl", "lua_library")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_list", "is_string", "is_tuple")

_DEFAULT_CPP_MAIN = target_utils.RootRuleTarget("tools/make_lar", "lua_main")

_INTERPRETERS = [
    _DEFAULT_CPP_MAIN,
    target_utils.RootRuleTarget("tools/make_lar", "lua_main_no_fb"),
]

_CPP_MAIN_SOURCE_TEMPLATE = """\
#include <stdlib.h>
#include <string.h>

#include <string>
#include <vector>

extern "C" int lua_main(int argc, char **argv);

static std::string join(const char *a, const char *b) {{
  std::string p;
  p += a;
  p += '/';
  p += b;
  return p;
}}

static std::string join(const std::string& a, const char * b) {{
  return join(a.c_str(), b);
}}

static std::string join(const std::string& a, const std::string& b) {{
  return join(a.c_str(), b.c_str());
}}

static std::string dirname(const std::string& a) {{
  return a.substr(0, a.rfind('/'));
}}

extern "C"
int run_starter(
    int argc,
    const char **argv,
    const char * /*main_module*/,
    const char *modules_dir,
    const char *py_modules_dir,
    const char *extension_suffix) {{

  if (modules_dir != NULL) {{

      std::string packagePath =
        join(modules_dir, "?.lua") + ';' +
        join(join(modules_dir, "?"), "init.lua");
      setenv("LUA_PATH", packagePath.c_str(), 1);

      std::string packageCPath =
        join(modules_dir, std::string("?.") + extension_suffix);
      setenv("LUA_CPATH", packageCPath.c_str(), 1);

  }}

  if (py_modules_dir != NULL) {{
      setenv("PYTHONPATH", py_modules_dir, 1);
      setenv("FB_LAR_INIT_PYTHON", "1", 1);
  }}

  std::vector<const char*> args;
  std::vector<std::string> argsStorage;
  args.push_back(argv[0]);
  args.insert(args.end(), {args});
  if ({run_file} != NULL) {{
    args.push_back("--");
    argsStorage.push_back(
      join(
        modules_dir == NULL ?
          dirname(std::string(argv[0])) :
          modules_dir,
        {run_file}));
    args.push_back(argsStorage.back().c_str());
  }}
  for (int i = 1; i < argc; i++) {{
    args.push_back(argv[i]);
  }}
  args.push_back(NULL);

  return lua_main(args.size() - 1, const_cast<char**>(args.data()));
}}
"""

def _cpp_repr_str(s):
    return '"' + s + '"'

def _cpp_repr_list(xs):
    return "{" + ", ".join([_cpp_repr(a) for a in xs]) + "}"

def _cpp_repr(a):
    if a == None:
        return "NULL"
    elif is_string(a):
        return _cpp_repr_str(a)
    elif is_tuple(a) or is_list(a):
        return _cpp_repr_list(a)
    else:
        fail("unexpected type")

def _create_cpp_main_library(
        base_path,
        name,
        base_module = None,
        interactive = False,
        cpp_main = None,
        cpp_main_args = (),
        run_file = None,
        allocator = "malloc",
        visibility = None):
    """
    Create the C/C++ main entry point.
    """
    _ignore = base_module
    args = []
    args.extend(cpp_main_args)
    if interactive:
        args.append("-i")

    cpp_main_source = (
        _CPP_MAIN_SOURCE_TEMPLATE.format(
            args = _cpp_repr(args),
            run_file = _cpp_repr(run_file),
        )
    )
    cpp_main_source_name = name + "-cpp-main-source"
    fb_native.genrule(
        name = cpp_main_source_name,
        visibility = get_visibility(visibility, cpp_main_source_name),
        out = name + ".cpp",
        cmd = (
            "echo -n {} > $OUT".format(shell.quote(cpp_main_source))
        ),
    )

    cpp_main_linker_flags = cpp_flags.get_extra_ldflags()

    # Setup platform default for compilation DB, and direct building.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)

    # Set the dependencies that linked into the C/C++ starter binary.
    out_deps = []

    # If a user-specified `cpp_main` is given, use that.  Otherwise,
    # fallback to the default.
    if cpp_main != None:
        out_deps.append(target_utils.parse_target(cpp_main, default_base_path = base_path))
    else:
        out_deps.append(_DEFAULT_CPP_MAIN)

    # Add in binary-specific link deps.
    out_deps.extend(
        cpp_common.get_binary_link_deps(
            base_path,
            name,
            cpp_main_linker_flags,
            allocator = allocator,
        ),
    )

    # Set the deps attr.
    cpp_main_deps, cpp_main_platform_deps = (
        src_and_dep_helpers.format_all_deps(out_deps)
    )

    cpp_main_name = name + "-cpp-main"

    fb_native.cxx_library(
        name = cpp_main_name,
        visibility = get_visibility(visibility, cpp_main_name),
        compiler_flags = cpp_flags.get_extra_cxxflags(),
        linker_flags = cpp_main_linker_flags,
        exported_linker_flags = [
            # Since we statically link in sanitizer/allocators libs, make sure
            # we export all their symbols on the dynamic symbols table.
            # Normally, the linker would take care of this for us, but we link
            # the cpp main binary with only it's minimal deps (rather than all
            # C/C++ deps for the Lua binary), so it may incorrectly decide to
            # not export some needed symbols.
            "-Wl,--export-dynamic",
        ],
        force_static = True,
        srcs = [":" + cpp_main_source_name],
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
        deps = cpp_main_deps,
        platform_deps = cpp_main_platform_deps,
    )

    return ":" + cpp_main_name

def _get_module(base_path, name, base_module = None):
    base_module = lua_common.get_lua_base_module(base_path, base_module = base_module)
    if base_module:
        return base_module.replace("/", ".") + "." + name
    return name

def _create_run_library(
        base_path,
        name,
        interactive = False,
        base_module = None,
        main_module = None,
        visibility = None):
    """
    Create the run file used by fbcode's custom Lua bootstrapper.
    """
    source_name = name + "-run-source"
    if interactive:
        source = ""
    else:
        source = (
            'require("fb.trepl.base").exec("{}")'.format(
                _get_module(
                    base_path,
                    main_module,
                    base_module = base_module,
                ),
            )
        )
    source_out = "_run.lua"
    fb_native.genrule(
        name = source_name,
        visibility = get_visibility(visibility, source_name),
        out = source_out,
        cmd = (
            "echo -n {} > $OUT".format(shell.quote(source))
        ),
    )

    lib_name = name + "-run"
    fb_native.lua_library(
        name = lib_name,
        visibility = get_visibility(visibility, lib_name),
        srcs = [":" + source_name],
        base_module = "",
        deps = [
            src_and_dep_helpers.convert_build_target(base_path, "//fblualib/trepl:base"),
        ],
    )

    return lib_name, source_out

def lua_binary(
        name,
        main_module = None,
        base_module = None,
        interactive = None,
        cpp_main = None,
        cpp_main_args = (),
        embed_deps = None,
        srcs = (),
        deps = (),
        external_deps = (),
        allocator = "malloc",
        visibility = None,
        binary_name = None,
        package_style = None,
        is_test = False):
    """
    Buckify a binary rule.
    """
    _ignore = embed_deps
    base_path = native.package_name()
    binary_name = binary_name or name

    platform = platform_utils.get_platform_for_base_path(base_path)

    attributes = {}

    dependencies = []

    # If we see any `srcs`, spin them off into a library rule and add that
    # as a dep.
    if srcs:
        lib_name = name + "-library"
        lua_library(
            name = lib_name,
            base_module = base_module,
            srcs = srcs,
            deps = deps,
            external_deps = external_deps,
            visibility = visibility,
        )
        dependencies.append(target_utils.RootRuleTarget(base_path, lib_name))
        deps = []
        external_deps = []

    # Parse out the `cpp_main` parameter.
    if cpp_main == None:
        cpp_main_dep = _DEFAULT_CPP_MAIN
    else:
        cpp_main_dep = target_utils.parse_target(cpp_main, default_base_path = base_path)

    # Default main_module = name
    if (main_module == None and
        interactive == None and
        cpp_main_dep in _INTERPRETERS):
        main_module = name

    # If a main module is specified, create a run file for it.
    run_file = None
    if main_module != None or interactive:
        lib, run_file = (
            _create_run_library(
                base_path,
                name,
                interactive = interactive,
                main_module = main_module,
                base_module = base_module,
                visibility = visibility,
            )
        )
        dependencies.append(target_utils.RootRuleTarget(base_path, lib))

    # Generate the native starter library.
    cpp_main_lib = (
        _create_cpp_main_library(
            base_path,
            name,
            base_module = base_module,
            interactive = interactive,
            cpp_main = cpp_main,
            cpp_main_args = cpp_main_args,
            run_file = run_file,
            allocator = allocator,
            visibility = visibility,
        )
    )

    # Tests depend on FB lua test lib.
    if is_test:
        dependencies.append(target_utils.RootRuleTarget("fblualib/luaunit", "luaunit"))

    # Add in `dep` and `external_deps` parameters to the dependency list.
    for dep in deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))
    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

    if dependencies:
        attributes["deps"], attributes["platform_deps"] = (
            src_and_dep_helpers.format_all_deps(dependencies)
        )

    fb_native.lua_binary(
        name = binary_name,
        visibility = get_visibility(visibility, binary_name),
        package_style = package_style,
        native_starter_library = cpp_main_lib,
        # We always use a dummy main module, since we pass in the actual main
        # module via the run file.
        main_module = "dummy",
        # We currently always use py2.
        python_platform = platform_utils.get_buck_python_platform(platform, major_version = 2),
        # Set platform.
        platform = platform_utils.get_buck_platform_for_base_path(base_path),
        **attributes
    )
