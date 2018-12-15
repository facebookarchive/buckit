load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_choice")
load("@fbcode_macros//build_defs/lib:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs/lib:build_info.bzl", "build_info")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs/lib:python_typing.bzl", "gen_typing_config", "get_typing_config_target")
load("@fbcode_macros//build_defs/lib:python_versioning.bzl", "python_versioning")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:string_macros.bzl", "string_macros")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_dict", "is_list")

_INTERPRETERS = [
    # name suffix, main module, dependencies
    ("interp", "libfb.py.python_interp", "//libfb/py:python_interp"),
    ("ipython", "libfb.py.ipython_interp", "//libfb/py:ipython_interp"),
    ("vs_debugger", "libfb.py.vs_debugger", "//libfb/py:vs_debugger"),
]

_MANIFEST_TEMPLATE = """\
import sys


class Manifest(object):

    def __init__(self):
        self._modules = None
        self.__file__ = __file__
        self.__name__ = __name__

    @property
    def modules(self):
        if self._modules is None:
            import os, sys
            modules = set()
            for root, dirs, files in os.walk(sys.path[0]):
                rel_root = os.path.relpath(root, sys.path[0])
                if rel_root == '.':
                    package_prefix = ''
                else:
                    package_prefix = rel_root.replace(os.sep, '.') + '.'

                for name in files:
                    base, ext = os.path.splitext(name)
                    # Note that this loop includes all *.so files, regardless
                    # of whether they are actually python modules or just
                    # regular dynamic libraries
                    if ext in ('.py', '.pyc', '.pyo', '.so'):
                        if rel_root == "." and base == "__manifest__":
                            # The manifest generation logic for normal pars
                            # does not include the __manifest__ module itself
                            continue
                        modules.add(package_prefix + base)
                # Skip __pycache__ directories
                try:
                    dirs.remove("__pycache__")
                except ValueError:
                    pass
            self._modules = sorted(modules)
        return self._modules

    fbmake = {{
        {fbmake}
    }}


sys.modules[__name__] = Manifest()
"""

def _get_version_universe(python_version):
    """
    Get the version universe for a specific python version

    Args:
        python_version: A `PythonVersion` that the universe should be fetched for

    Returns:
        The first third-party version universe string that corresponds to the python version
    """
    return third_party.get_version_universe([("python", python_version.version_string)])

def _interpreter_binaries(
        name,
        buck_cxx_platform,
        python_version,
        python_platform,
        deps,
        platform_deps,
        preload_deps,
        visibility):
    """
    Generate rules to build intepreter helpers.

    Args:
        name: The base name for the interpreter rules
        buck_cxx_platform: The buck-formatted cxx_platform to use for the interpreter binary
        python_version: A `PythonVersion` struct for the version of python to use
        python_platform: The python platform to pass to buck
        deps: The deps to pass to the binary in addition to interpeter deps
        platform_deps: The platform deps to pass to buck
        preload_deps: The preload deps to pass to buck
        visibility: The visibilty of the rule

    Returns:
        The list of names of all generated rules
    """

    rule_names = []

    for interp, interp_main_module, interp_dep in _INTERPRETERS:
        rule_name = name + "-" + interp
        fb_native.python_binary(
            name = rule_name,
            visibility = visibility,
            main_module = interp_main_module,
            cxx_platform = buck_cxx_platform,
            platform = python_platform,
            version_universe = _get_version_universe(python_version),
            deps = [interp_dep] + deps,
            platform_deps = platform_deps,
            preload_deps = preload_deps,
            package_style = "inplace",
        )
        rule_names.append(rule_name)
    return rule_names

def _get_interpreter_for_platform(python_platform):
    """ Get the interpreter to use for a buck-native python platform """
    return native.read_config("python#" + python_platform, "interpreter")

def _get_build_info(
        base_path,
        name,
        fbconfig_rule_type,
        main_module,
        fbcode_platform,
        python_platform):
    """
    Return the build info attributes to install for python rules.

    Args:
        base_path: The package for the current build file
        name: The name of the rule being built
        fbconfig_rule_type: The name of the main rule being built; used for build_info
        main_module: The python main module of the binary/test
        fbcode_platform: The fbcode platform used for the binary/test
        python_platform: The buck-compatible python_platform that is being used

    Returns:
        A dictionary of key/value strings to put into a build manifest
    """

    interpreter = _get_interpreter_for_platform(python_platform)

    # Iteration order is deterministic for dictionaries in buck/skylark
    py_build_info = {
        "build_tool": "buck",
        "main_module": main_module,
        "par_style": "live",
        "python_command": interpreter,
        "python_home": paths.dirname(paths.dirname(interpreter)),
    }

    # Include the standard build info, converting the keys to the names we
    # use for python.
    key_mappings = {
        "package_name": "package",
        "package_version": "version",
        "rule": "build_rule",
        "rule_type": "build_rule_type",
    }
    info = build_info.get_build_info(
        base_path,
        name,
        fbconfig_rule_type,
        fbcode_platform,
    )
    for key in build_info.BUILD_INFO_KEYS:
        py_build_info[key_mappings.get(key, key)] = getattr(info, key)

    return py_build_info

def _manifest_library(
        base_path,
        name,
        fbconfig_rule_type,
        main_module,
        fbcode_platform,
        python_platform,
        visibility):
    """
    Build the rules that create the `__manifest__` module.

    Args:
        base_path: The package of this rule
        name: The name of the primary rule that was generated
        fbconfig_rule_type: The name of the main rule being built; used for build_info
        main_module: The main module of the python binary/test
        fbcode_platform: The fbcode platform to use in build info
        python_platform: The buck-compatible python platform to use
        visibility: The visiblity for the main python_library

    Returns:
        The name of a library that contains a __mainfest__.py with
        build information in it.
    """

    build_info = _get_build_info(
        base_path,
        name,
        fbconfig_rule_type,
        main_module,
        fbcode_platform,
        python_platform,
    )

    fbmake = "\n        ".join([
        "{!r}: {!r},".format(k, v)
        for k, v in build_info.items()
    ])
    manifest = _MANIFEST_TEMPLATE.format(fbmake = fbmake)

    manifest_name = name + "-manifest"
    manifest_lib_name = name + "-manifest-lib"

    fb_native.genrule(
        name = manifest_name,
        labels = ["generated"],
        visibility = None,
        out = name + "-__manifest__.py",
        cmd = "echo -n {} > $OUT".format(shell.quote(manifest)),
    )

    fb_native.python_library(
        name = manifest_lib_name,
        labels = ["generated"],
        visibility = visibility,
        base_module = "",
        srcs = {"__manifest__.py": ":" + manifest_name},
    )

    return manifest_lib_name

def _file_to_python_module(src, base_module):
    """Python implementation of Buck's toModuleName().

    Original in com.facebook.buck.python.PythonUtil.toModuleName.
    """
    src = paths.join(base_module, src)
    src, ext = paths.split_extension(src)
    return src.replace("/", ".")  # sic, not os.sep

def _test_modules_library(
        base_path,
        library_name,
        library_srcs,
        library_base_module,
        visibility,
        generate_test_modules):
    """"
    Create the rule that generates a __test_modules__.py file for a library

    Args:
        base_path: The package for the current build file
        library_name: The name of the original library that was built
        library_srcs: The list of srcs (files or labels) that were given to the
                      original library that this test_modules_library is for
        library_base_module: The base_module of the original library
        visibility: The visibility for this rule
        generate_test_modules: Whether to actually materialize the rule. If False,
                               just return the name of the rule

    Returns:
        The name of the generated python library that contains __test_modules__.py
    """

    testmodules_library_name = library_name + "-testmodules-lib"

    # If we don't actually want to generate the library (generate_test_modules),
    # at least return the name
    if not generate_test_modules:
        return testmodules_library_name

    lines = ["TEST_MODULES = ["]
    for src in sorted(library_srcs):
        lines.append(
            '    "{}",'.format(
                _file_to_python_module(src, library_base_module or base_path),
            ),
        )
    lines.append("]")

    genrule_name = library_name + "-testmodules"
    fb_native.genrule(
        name = genrule_name,
        visibility = None,
        out = library_name + "-__test_modules__.py",
        cmd = " && ".join([
            "echo {} >> $OUT".format(shell.quote(line))
            for line in lines
        ]),
    )

    fb_native.python_library(
        name = testmodules_library_name,
        visibility = visibility,
        base_module = "",
        deps = ["//python:fbtestmain", ":" + library_name],
        srcs = {"__test_modules__.py": ":" + genrule_name},
    )
    return testmodules_library_name

def _typecheck_test(
        name,
        main_module,
        buck_cxx_platform,
        python_platform,
        python_version,
        deps,
        platform_deps,
        preload_deps,
        typing_options,
        visibility,
        emails,
        library_target,
        library_versioned_srcs,
        library_srcs,
        library_resources,
        library_base_module):
    """
    Create a test and associated libraries for running typechecking

    Args:
        name: The name of the original binary/test to run typechecks on
        main_module: The main module of hte binary/test
        buck_cxx_platform: The buck-formatted cxx_platform to use for the interpreter binary
        python_version: A `PythonVersion` struct for the version of python to use
        python_platform: The python platform to pass to buck
        deps: The deps to pass to the binary in addition to interpeter deps
        platform_deps: The platform deps to pass to buck
        preload_deps: The preload deps to pass to buck
        typing_options: A comma delimited list of strings that configure typing for
                        this binary/library
        visibility: The visibilty of the rule
        library_target: The fully qualified target for the original library used in
                        the binary/test. This is used to determine whether the following
                        library_* properties are used in the final test rule
        library_versioned_srcs: The versioned_srcs property from the library used
                                to create the original binary/test. This should be the
                                final value passed to buck: No intermediate representations
        library_srcs: The srcs property from the library used to create the original
                      binary/test. This should be the final value passed to
                      buck: No intermediate representations
        library_resources: The resources property from the library used to create the
                           original binary/test. This should be the final value passed
                           to buck: No intermediate representations
        library_base_module: The base_module property from the library used  to create
                             the original binary/test. This should be the final
                             value passed to buck: No intermediate representations

    Returns:
        The name of the test library that was created
    """

    typing_config = get_typing_config_target()

    typecheck_deps = deps[:]
    if ":python_typecheck-library" not in typecheck_deps:
        # Buck doesn't like duplicate dependencies.
        typecheck_deps.append("//libfb/py:python_typecheck-library")

    if not typing_config:
        typecheck_deps.append("//python/typeshed_internal:global_mypy_ini")

    env = {}

    # If the passed library is not a dependency, add its sources here.
    # This enables python_unittest targets to be type-checked, too.
    add_library_attrs = library_target not in typecheck_deps
    if not add_library_attrs:
        library_versioned_srcs = None
        library_srcs = None
        library_resources = None
        library_base_module = None

    if main_module not in ("__fb_test_main__", "libfb.py.testslide.unittest"):
        # Tests are properly enumerated from passed sources (see above).
        # For binary targets, we need this subtle hack to let
        # python_typecheck know where to start type checking the program.
        env["PYTHON_TYPECHECK_ENTRY_POINT"] = main_module

    typing_options_list = [
        option.strip()
        for option in typing_options.split(",")
    ] if typing_options else []
    use_pyre = typing_options and "pyre" in typing_options_list

    if use_pyre:
        typing_options_list.remove("pyre")
        typing_options = ",".join(typing_options_list)
        env["PYRE_ENABLED"] = "1"

    if typing_config:
        cmd = "$(exe {}) gather ".format(typing_config)
        if use_pyre:
            genrule_name = name + "-typing=pyre.json"
            genrule_out = "pyre.json"
            cmd += "--pyre=True "
        else:
            genrule_name = name + "-typing=mypy.ini"
            genrule_out = "mypy.ini"
        if typing_options:
            cmd += '--options="{}" '.format(typing_options)
        cmd += "$(location {}-typing) $OUT".format(library_target)

        fb_native.genrule(
            name = genrule_name,
            out = genrule_out,
            cmd = cmd,
            visibility = visibility,
        )

        if use_pyre:
            typing_library_name = name + "-pyre_json"
        else:
            typing_library_name = name + "-mypy_ini"

        fb_native.python_library(
            name = typing_library_name,
            visibility = visibility,
            base_module = "",
            srcs = [":" + genrule_name],
        )
        typecheck_deps.append(":" + typing_library_name)

    typecheck_rule_name = name + "-typecheck"
    fb_native.python_test(
        name = typecheck_rule_name,
        main_module = "python_typecheck",
        cxx_platform = buck_cxx_platform,
        platform = python_platform,
        deps = typecheck_deps,
        platform_deps = platform_deps,
        preload_deps = preload_deps,
        package_style = "inplace",
        # TODO(ambv): labels here shouldn't be hard-coded.
        labels = ["buck", "python"],
        version_universe = _get_version_universe(python_version),
        contacts = emails,
        visibility = visibility,
        env = env,
        versioned_srcs = library_versioned_srcs,
        srcs = library_srcs,
        resources = library_resources,
        base_module = library_base_module,
    )
    return typecheck_rule_name

def _monkeytype_binary(
        rule_type,
        attributes,
        library_name):
    """
    Create a python binary/test that enables monkeytype but otherwise looks like another binary/test

    Args:
        rule_type: The type of rule to create (python_binary or python_test)
        attributes: The attributes of the original binary/test that we are enabling
                    monkeytype for. These should be final values passed to buck,
                    not intermediaries, as they are copied directly into a
        library_name: The name of the implicit library created for the binary/test
    """

    name = attributes["name"]
    visibility = attributes.get("visibility")
    lib_main_module_attrs_name = None
    if "main_module" in attributes:
        # we need to preserve the original main_module, so we inject a
        # library with a module for it that the main wrapper picks up
        main_module_name = name + "-monkeytype_main_module"
        script = (
            "#!/usr/bin/env python3\n\n" +
            "def monkeytype_main_module() -> str:\n" +
            "    return '{}'\n".format(attributes["main_module"])
        )

        fb_native.genrule(
            name = main_module_name,
            visibility = visibility,
            out = name + "-__monkeytype_main_module__.py",
            cmd = "echo {} > $OUT".format(shell.quote(script)),
        )

        lib_main_module_attrs_name = name + "-monkeytype_main_module-lib"
        fb_native.python_library(
            name = lib_main_module_attrs_name,
            visibility = visibility,
            base_module = "",
            deps = ["//python:fbtestmain", ":" + name],
            srcs = {
                "__monkeytype_main_module__.py": ":" + main_module_name,
            },
        )

    # Create a variant of the target that is running with monkeytype
    if rule_type == "python_binary":
        wrapper_rule_constructor = fb_native.python_binary
    elif rule_type == "python_test":
        wrapper_rule_constructor = fb_native.python_test
    else:
        fail("Invalid rule type specified: " + rule_type)

    wrapper_attrs = dict(attributes)
    wrapper_attrs["name"] = name + "-monkeytype"
    wrapper_attrs["visibility"] = visibility
    if "deps" in wrapper_attrs:
        wrapper_deps = list(wrapper_attrs["deps"])
    else:
        wrapper_deps = []
    library_target = ":" + library_name
    if library_target not in wrapper_deps:
        wrapper_deps.append(library_target)
    stub_gen_deps = list(wrapper_deps)

    if "//python/monkeytype:main_wrapper" not in wrapper_deps:
        wrapper_deps.append("//python/monkeytype/tools:main_wrapper")
    if lib_main_module_attrs_name != None:
        wrapper_deps.append(":" + lib_main_module_attrs_name)
    wrapper_attrs["deps"] = wrapper_deps
    wrapper_attrs["base_module"] = ""
    wrapper_attrs["main_module"] = "python.monkeytype.tools.main_wrapper"
    wrapper_rule_constructor(**wrapper_attrs)

    if "//python/monkeytype/tools:stubs_lib" not in wrapper_deps:
        stub_gen_deps.append("//python/monkeytype/tools:stubs_lib")

    # And create a target that can be used for stub creation
    fb_native.python_binary(
        name = name + "-monkeytype-gen-stubs",
        visibility = visibility,
        main_module = "python.monkeytype.tools.get_stub",
        cxx_platform = attributes["cxx_platform"],
        platform = attributes["platform"],
        deps = stub_gen_deps,
        platform_deps = attributes["platform_deps"],
        preload_deps = attributes["preload_deps"],
        package_style = "inplace",
        version_universe = attributes["version_universe"],
    )

def _analyze_import_binary(
        name,
        buck_cxx_platform,
        python_platform,
        python_version,
        deps,
        platform_deps,
        preload_deps,
        visibility):
    """ Generate a binary to analyze the imports of a given python library """
    generate_imports_deps = list(deps)
    if ":generate_par_imports" not in generate_imports_deps:
        generate_imports_deps.append("//libfb/py:generate_par_imports")

    if ":parutil" not in generate_imports_deps:
        generate_imports_deps.append("//libfb/py:parutil")

    version_universe = _get_version_universe(python_version)

    generate_par_name = name + "-generate-imports"
    fb_native.python_binary(
        name = generate_par_name,
        main_module = "libfb.py.generate_par_imports",
        cxx_platform = buck_cxx_platform,
        platform = python_platform,
        deps = generate_imports_deps,
        platform_deps = platform_deps,
        preload_deps = preload_deps,
        # TODO(ambv): labels here shouldn't be hard-coded.
        labels = ["buck", "python"],
        version_universe = version_universe,
        visibility = visibility,
    )

    genrule_name = name + "-gen-rule"
    fb_native.genrule(
        name = genrule_name,
        srcs = [":" + generate_par_name],
        out = "{}-imports_file.py".format(name),
        cmd = '$(exe :{}) >"$OUT"'.format(generate_par_name),
    )

    lib_name = name + "-analyze-lib"
    fb_native.python_library(
        name = lib_name,
        srcs = {"imports_file.py": ":" + genrule_name},
        base_module = "",
        deps = [":" + genrule_name],
    )
    analyze_deps = list(deps)
    analyze_deps.append(":" + lib_name)

    if ":analyze_par_imports" not in analyze_deps:
        analyze_deps.append("//libfb/py:analyze_par_imports")

    fb_native.python_binary(
        name = name + "-analyze-imports",
        main_module = "libfb.py.analyze_par_imports",
        cxx_platform = buck_cxx_platform,
        platform = python_platform,
        deps = analyze_deps,
        platform_deps = platform_deps,
        preload_deps = preload_deps,
        # TODO(ambv): labels here shouldn't be hard-coded.
        labels = ["buck", "python"],
        version_universe = version_universe,
        visibility = visibility,
    )

_GEN_SRCS_LINK = "https://fburl.com/203312823"

def _parse_srcs(base_path, param, srcs):  # type: (str, str, Union[List[str], Dict[str, str]]) -> Dict[str, Union[str, RuleTarget]]
    """
    Converts `srcs` to a `srcs` dictionary for use in python_* rule

    Fails if a RuleTarget object is passed in, but a source file name cannot be
    determined

    Args:
        base_path: The package for the rule
        param: The name of the parameter being parsed. Used in error messages
        srcs: Either a dictionary of file/target -> destination in the library, or
              a list of source files or RuleTarget objects that the source named
              can be divined from.

    Returns:
        A mapping of destination filename -> file str / RuleTarget
    """

    # Parse sources in dict form.
    if is_dict(srcs) or hasattr(srcs, "items"):
        out_srcs = (
            src_and_dep_helpers.parse_source_map(
                base_path,
                {v: k for k, v in srcs.items()},
            )
        )

        # Parse sources in list form.
    else:
        out_srcs = {}

        # Format sources into a dict of logical name of value.
        for src in src_and_dep_helpers.parse_source_list(base_path, srcs):
            # Path names are the same as path values.
            if not target_utils.is_rule_target(src):
                out_srcs[src] = src
                continue

            # If the source comes from a `custom_rule`/`genrule`, and the
            # user used the `=` notation which encodes the source's "name",
            # we can extract and use that.
            if "=" in src.name:
                name = src.name.rsplit("=", 1)[1]
                out_srcs[name] = src
                continue

            # Otherwise, we don't have a good way of deducing the name.
            # This actually looks to be pretty rare, so just throw a useful
            # error prompting the user to use the `=` notation above, or
            # switch to an explicit `dict`.
            fail(
                'parameter `{}`: cannot infer a "name" to use for ' +
                "`{}`. If this is an output from a `custom_rule`, " +
                "consider using the `<rule-name>=<out>` notation instead. " +
                "Otherwise, please specify this parameter as `dict` " +
                'mapping sources to explicit "names" (see {} for details).'
                    .format(param, target_utils.target_to_label(src), _GEN_SRCS_LINK),
            )

    return out_srcs

def _parse_gen_srcs(base_path, srcs):  # type: (str, Union[List[str], Dict[str, str]]) -> Dict[str, Union[str, RuleTarget]]
    """
    Parse the given sources as input to the `gen_srcs` parameter.
    """

    out_srcs = _parse_srcs(base_path, "gen_srcs", srcs)

    # Do a final pass to verify that all sources in `gen_srcs` are rule
    # references.
    for src in out_srcs.values():
        if not target_utils.is_rule_target(src):
            fail(
                "parameter `gen_srcs`: `{}` must be a reference to rule " +
                "that generates a source (e.g. `//foo:bar`, `:bar`) " +
                " (see {} for details)."
                    .format(src, GEN_SRCS_LINK),
            )

    return out_srcs

def _get_par_build_args(
        base_path,
        name,
        rule_type,
        platform,
        argcomplete = None,
        strict_tabs = None,
        compile = None,
        par_style = None,
        strip_libpar = None,
        needed_coverage = None,
        python = None):
    """
    Return the arguments we need to pass to the PAR builder wrapper.
    """

    build_args = []
    build_mode = config.get_build_mode()

    if config.get_use_custom_par_args():
        # Arguments that we wanted directly threaded into `make_par`.
        passthrough_args = []
        if argcomplete == True:
            passthrough_args.append("--argcomplete")
        if strict_tabs == False:
            passthrough_args.append("--no-strict-tabs")
        if compile == False:
            passthrough_args.append("--no-compile")
            passthrough_args.append("--store-source")
        elif compile == "with-source":
            passthrough_args.append("--store-source")
        elif compile != True and compile != None:
            fail(
                (
                    "Invalid value {} for `compile`, must be True, False, " +
                    '"with-source", or None (default)'
                ).format(compile),
            )
        if par_style != None:
            passthrough_args.append("--par-style=" + par_style)
        if needed_coverage != None or coverage.get_coverage():
            passthrough_args.append("--store-source")
        if build_mode.startswith("opt"):
            passthrough_args.append("--optimize")

        # Add arguments to populate build info.
        mode = build_info.get_build_info_mode(base_path, name)
        if mode == "none":
            fail("Invalid build info mode specified")
        info = (
            build_info.get_explicit_build_info(
                base_path,
                name,
                mode,
                rule_type,
                platform,
                compiler.get_compiler_for_current_buildfile(),
            )
        )
        passthrough_args.append(
            "--build-info-build-mode=" + info.build_mode,
        )
        passthrough_args.append("--build-info-build-tool=buck")
        if info.package_name != None:
            passthrough_args.append(
                "--build-info-package-name=" + info.package_name,
            )
        if info.package_release != None:
            passthrough_args.append(
                "--build-info-package-release=" + info.package_release,
            )
        if info.package_version != None:
            passthrough_args.append(
                "--build-info-package-version=" + info.package_version,
            )
        passthrough_args.append("--build-info-platform=" + info.platform)
        passthrough_args.append("--build-info-rule-name=" + info.rule)
        passthrough_args.append("--build-info-rule-type=" + info.rule_type)

        build_args.extend(["--passthrough=" + a for a in passthrough_args])

        # Arguments for stripping libomnibus. dbg builds should never strip.
        if not build_mode.startswith("dbg"):
            if strip_libpar == True:
                build_args.append("--omnibus-debug-info=strip")
            elif strip_libpar == "extract":
                build_args.append("--omnibus-debug-info=extract")
            else:
                build_args.append("--omnibus-debug-info=separate")

        # Set an explicit python interpreter.
        if python != None:
            build_args.append("--python-override=" + python)

    return build_args

def _associated_targets_library(base_path, name, deps, visibility):
    """
    Associated Targets are buck rules that need to be built, when This
    target is built, but are not a code dependency. Which is why we
    wrap them in a cxx_library so they could never be a code dependency

    TODO: Python just needs the concept of runtime deps if it doesn't have it.
          Also, what is the actual use case for this?
    """
    rule_name = name + "-build_also"
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    fb_native.cxx_library(
        name = rule_name,
        visibility = visibility,
        deps = deps,
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
    )
    return rule_name

def _jemalloc_malloc_conf_library(base_path, name, malloc_conf, deps, visibility):
    """
    Build a rule which wraps the JEMalloc allocator and links default
    configuration via the `jemalloc_conf` variable.
    """

    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    jemalloc_config_line = ",".join([
        "{}:{}".format(k, v)
        for k, v in sorted(malloc_conf.items())
    ])

    src_rule_name = "__{}_jemalloc_conf_src__".format(name)
    fb_native.genrule(
        name = src_rule_name,
        visibility = visibility,
        out = "jemalloc_conf.c",
        cmd = 'echo \'const char* malloc_conf = "{}";\' > "$OUT"'.format(jemalloc_config_line),
    )

    deps, platform_deps = src_and_dep_helpers.format_all_deps(deps)

    lib_rule_name = "__{}_jemalloc_conf_lib__".format(name)
    fb_native.cxx_library(
        name = lib_rule_name,
        visibility = visibility,
        srcs = [":" + src_rule_name],
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
        deps = deps,
        platform_deps = platform_deps,
    )

    return target_utils.RootRuleTarget(base_path, lib_rule_name)

def _convert_needed_coverage_spec(base_path, spec):
    """
    Converts `needed_coverage` from fbcode's spec into the buck native spec

    Args:
        base_path: The base path for this rule; used to get fully qualified targets
        spec: A tuple of (<needed percentage as int>, <target as a string>)

    Returns:
        A buck-compatible spec. This is a tuple of two elements if no source name
        is detected in the target name (with an =) or three elements if it is
        detected in the form of
        (<percentage as int>, <full target as string>, <file as string>?)
    """
    if len(spec) != 2:
        fail((
            "parameter `needed_coverage`: `{}` must have exactly 2 " +
            "elements, a ratio and a target."
        ).format(spec))

    ratio, target = spec
    if "=" not in target:
        return (
            ratio,
            src_and_dep_helpers.convert_build_target(base_path, target),
        )
    target, path = target.rsplit("=", 1)
    return (ratio, src_and_dep_helpers.convert_build_target(base_path, target), path)

def _should_generate_interp_rules(helper_deps):
    """
    Return whether we should generate the interp helpers.

    This is controlled by both the mode, the property, and buckconfig settings

    Args:
        helper_deps: The value of the `helper_deps` attribute on the users rule.
                     Should be True or False
    """

    # We can only work in @mode/dev
    if not config.get_build_mode().startswith("dev"):
        return False

    # Our current implementation of the interp helpers is costly when using
    # omnibus linking, only generate these if explicitly set via config or TARGETS
    config_setting = read_bool("python", "helpers", required = False)

    if config_setting == None:
        # No CLI option is set, respect the TARGETS file option.
        return helper_deps

    return config_setting

def _preload_deps(base_path, name, allocator, jemalloc_conf = None, visibility = None):
    """
    Add C/C++ deps which need to preloaded by Python binaries.

    Returns:
        A list of additional dependencies (as strings) which should be added to the
        python binary
    """

    deps = []
    sanitizer = sanitizers.get_sanitizer()

    # If we're using sanitizers, add the dep on the sanitizer-specific
    # support library.
    if sanitizer != None:
        sanitizer = sanitizers.get_short_name(sanitizer)
        deps.append(
            target_utils.RootRuleTarget(
                "tools/build/sanitizers",
                "{}-py".format(sanitizer),
            ),
        )

    # Generate sanitizer configuration even if sanitizers are not used
    deps.append(
        cpp_common.create_sanitizer_configuration(
            base_path,
            name,
            enable_lsan = False,
        ),
    )

    # If we're using an allocator, and not a sanitizer, add the allocator-
    # specific deps.
    if allocator != None and sanitizer == None:
        allocator_deps = allocators.get_allocator_deps(allocator)
        if allocator.startswith("jemalloc") and jemalloc_conf != None:
            conf_dep = _jemalloc_malloc_conf_library(
                base_path,
                name,
                jemalloc_conf,
                allocator_deps,
                visibility,
            )
            allocator_deps = [conf_dep]
        deps.extend(allocator_deps)

    return deps

def _get_ldflags(base_path, name, fbconfig_rule_type, strip_libpar = True):
    """
    Return ldflags to use when linking omnibus libraries in python binaries.
    """

    # We override stripping for python binaries unless we're in debug mode
    # (which doesn't get stripped by default).  If either `strip_libpar`
    # is set or any level of stripping is enabled via config, we do full
    # stripping.
    strip_mode = cpp_common.get_strip_mode(base_path, name)
    if (not config.get_build_mode().startswith("dbg") and
        (strip_mode != "none" or strip_libpar == True)):
        strip_mode = "full"

    return cpp_common.get_ldflags(
        base_path,
        name,
        fbconfig_rule_type,
        strip_mode = strip_mode,
    )

def _get_package_style():
    """
    Get the package_style to use for binary rules from the configuration

    See https://buckbuild.com/rule/python_binary.html#package_style
    """
    return read_choice(
        "python",
        "package_style",
        ("inplace", "standalone"),
        "standalone",
    )

def _implicit_python_library(
        name,
        is_test_companion,
        base_module = None,
        srcs = (),
        versioned_srcs = (),
        gen_srcs = (),
        deps = (),
        tests = (),
        tags = (),
        external_deps = (),
        visibility = None,
        resources = (),
        cpp_deps = (),
        py_flavor = "",
        version_subdirs = None):  # Not used for now, will be used in a subsequent diff
    """
    Creates a python_library and all supporting libraries

    This library may or may not be consumed as a companion library to a
    python_binary, or a python_test. The attributes returned vary based on how
    it will be used.

    Args:
        name: The name of this library
        is_test_companion: Whether this library is being created and consumed
                           directly by a test rule
        base_module: The basemodule for the library (https://buckbuild.com/rule/python_library.html#base_module)
        srcs: A sequence of sources/targets to use as srcs. Note that only files
              ending in .py are considered sources. All other srcs are added as
              resources. Note if this is a dictionary, the key and value are swapped
              from the official buck implementation. That is,this rule expects
              {<src>: <destination in the library>}
        versioned_srcs: If provided, a list of tuples of
                        (<python version constraint string>, <srcs as above>)
                        These sources are then added to the versioned_srcs attribute
                        in the library
        gen_srcs: DEPRECATED A list of srcs that come from `custom_rule`s to be
                  merged into the final srcs list.
        deps: A sequence of dependencies for the library. These should only be python
              libraries, as python's typing support assumes that dependencies also
              have a companion -typing rule
        tests: The targets that test this library
        tags: Arbitrary metadata to attach to this library. See https://buckbuild.com/rule/python_library.html#labels
        external_deps: A sequence of tuples of external dependencies
        visibility: The visibility of the library
        resources: A sequence of sources/targets that should be explicitly added
                   as resoruces. Note that if a dictionary is used, the key and
                   value are swapped from the official buck implementation. That is,
                   this rule expects {<src>: <destination in the library>}
        cpp_deps: A sequence of C++ library depenencies that will be loaded at
                  runtime
        py_flavor: The flavor of python to use. By default ("") this is cpython
        version_subdirs: A sequence of tuples of
                         (<buck version constring>, <version subdir>). This points
                         to the subdirectory (or "") that each version constraint
                         uses. This helps us rewrite things like versioned_srcs for
                         third-party2 targets.

    Returns:
        The kwargs to pass to a native.python_library rule
    """
    base_path = native.package_name()
    attributes = {}
    attributes["name"] = name

    # Normalize all the sources from the various parameters.
    parsed_srcs = {}  # type: Dict[str, Union[str, RuleTarget]]
    parsed_srcs.update(_parse_srcs(base_path, "srcs", srcs))
    parsed_srcs.update(_parse_gen_srcs(base_path, gen_srcs))

    # Parse the version constraints and normalize all source paths in
    # `versioned_srcs`:
    parsed_versioned_srcs = [
        (
            python_versioning.python_version_constraint(pvc),
            _parse_srcs(base_path, "versioned_srcs", vs),
        )
        for pvc, vs in versioned_srcs
    ]

    # Contains a mapping of platform name to sources to use for that
    # platform.
    all_versioned_srcs = []

    # If we're TP project, install all sources via the `versioned_srcs`
    # parameter. `py_flavor` is ignored since flavored Pythons are only
    # intended for use by internal projects.
    if third_party.is_tp2(base_path):
        if version_subdirs == None:
            fail("`version_subdirs` must be specified on third-party projects")

        # TP2 projects have multiple "pre-built" source dirs, so we install
        # them via the `versioned_srcs` parameter along with the versions
        # of deps that was used to build them, so that Buck can select the
        # correct one based on version resolution.
        for constraints, subdir in version_subdirs:
            build_srcs = [parsed_srcs]
            if parsed_versioned_srcs:
                py_vers = None
                for target, constraint_version in constraints.items():
                    if target.endswith("/python:__project__"):
                        py_vers = python_versioning.python_version(constraint_version)

                # 'is None' can become == None when the custom version classes
                # go away
                if py_vers == None:
                    fail("Could not get python version for versioned_srcs")
                build_srcs.extend([
                    dict(vs)
                    for vc, vs in parsed_versioned_srcs
                    if python_versioning.constraint_matches(vc, py_vers, check_minor = True)
                ])

            vsrc = {}
            for build_src in build_srcs:
                for name, src in build_src.items():
                    if target_utils.is_rule_target(src):
                        vsrc[name] = src
                    else:
                        vsrc[name] = paths.join(subdir, src)

            all_versioned_srcs.append((constraints, vsrc))

        # Reset `srcs`, since we're using `versioned_srcs`.
        parsed_srcs = {}

        # If we're an fbcode project, and `py_flavor` is not specified, then
        # keep the regular sources parameter and only use the `versioned_srcs`
        # parameter for the input parameter of the same name; if `py_flavor` is
        # specified, then we have to install all sources via `versioned_srcs`

    else:
        pytarget = third_party.get_tp2_project_target("python")
        platforms = platform_utils.get_platforms_for_host_architecture()

        # Iterate over all potential Python versions and collect srcs for
        # each version:
        for pyversion in python_versioning.get_all_versions():
            if not python_versioning.version_supports_flavor(pyversion, py_flavor):
                continue

            ver_srcs = {}
            if py_flavor:
                ver_srcs.update(parsed_srcs)

            for constraint, pvsrcs in parsed_versioned_srcs:
                constraint = python_versioning.normalize_constraint(constraint)
                if python_versioning.constraint_matches(constraint, pyversion):
                    ver_srcs.update(pvsrcs)
            if ver_srcs:
                all_versioned_srcs.append(
                    (
                        {
                            target_utils.target_to_label(pytarget, fbcode_platform = p): pyversion.version_string
                            for p in platforms
                            if python_versioning.platform_has_version(p, pyversion)
                        },
                        ver_srcs,
                    ),
                )

        if py_flavor:
            parsed_srcs = {}

    attributes["base_module"] = base_module

    if parsed_srcs:
        # Need to split the srcs into srcs & resources as Buck
        # expects all test srcs to be python modules.
        if is_test_companion:
            formatted_srcs = src_and_dep_helpers.format_source_map({
                k: v
                for k, v in parsed_srcs.iteritems()
                if k.endswith(".py")
            })
            formatted_resources = src_and_dep_helpers.format_source_map({
                k: v
                for k, v in parsed_srcs.iteritems()
                if not k.endswith(".py")
            })
            attributes["resources"] = formatted_resources.value
            attributes["platform_resources"] = formatted_resources.platform_value
        else:
            formatted_srcs = src_and_dep_helpers.format_source_map(parsed_srcs)
        attributes["srcs"] = formatted_srcs.value
        attributes["platform_srcs"] = formatted_srcs.platform_value

    # Emit platform-specific sources.  We split them between the
    # `platform_srcs` and `platform_resources` parameter based on their
    # extension, so that directories with only resources don't end up
    # creating stray `__init__.py` files for in-place binaries.
    out_versioned_srcs = []
    out_versioned_resources = []
    for vcollection, ver_srcs in all_versioned_srcs:
        out_srcs = {}
        out_resources = {}
        non_platform_ver_srcs = src_and_dep_helpers.without_platforms(
            src_and_dep_helpers.format_source_map(ver_srcs),
        )
        for dst, src in non_platform_ver_srcs.items():
            if dst.endswith(".py") or dst.endswith(".so"):
                out_srcs[dst] = src
            else:
                out_resources[dst] = src
        out_versioned_srcs.append((vcollection, out_srcs))
        out_versioned_resources.append((vcollection, out_resources))

    if out_versioned_srcs:
        attributes["versioned_srcs"] = \
            python_versioning.add_flavored_versions(out_versioned_srcs)
    if out_versioned_resources:
        attributes["versioned_resources"] = \
            python_versioning.add_flavored_versions(out_versioned_resources)

    dependencies = []
    if third_party.is_tp2(base_path):
        dependencies.append(
            target_utils.target_to_label(
                third_party.get_tp2_project_target(
                    third_party.get_tp2_project_name(base_path),
                ),
                fbcode_platform = third_party.get_tp2_platform(base_path),
            ),
        )
    for target in deps:
        dependencies.append(
            src_and_dep_helpers.convert_build_target(base_path, target),
        )
    if cpp_deps:
        dependencies.extend(cpp_deps)
    if dependencies:
        attributes["deps"] = dependencies

    attributes["tests"] = tests

    if visibility != None:
        attributes["visibility"] = visibility

    if external_deps:
        attributes["platform_deps"] = (
            src_and_dep_helpers.format_platform_deps(
                [
                    src_and_dep_helpers.normalize_external_dep(
                        dep,
                        lang_suffix = "-py",
                        parse_version = True,
                    )
                    for dep in external_deps
                ],
                # We support the auxiliary versions hack for neteng/Django.
                deprecated_auxiliary_deps = True,
            )
        )

    attributes["labels"] = tags

    # The above code does a magical dance to split `gen_srcs`, `srcs`,
    # and `versioned_srcs` into pure-Python `srcs` and "everything else"
    # `resources`.  In practice, it drops `__init__.py` into non-Python
    # data included with Python libraries, whereas `resources` does not.
    attributes.setdefault("resources", {}).update({
        # For resources of the form {":target": "dest/path"}, we have to
        # format the parsed `RuleTarget` struct as a string before
        # passing it to Buck.
        k: src_and_dep_helpers.format_source(v)
        for k, v in _parse_srcs(
            base_path,
            "resources",
            resources,
        ).items()
    })

    return attributes

def _convert_library(
        is_test,
        is_library,
        base_path,
        name,
        base_module,
        check_types,
        cpp_deps,
        deps,
        external_deps,
        gen_srcs,
        py_flavor,
        resources,
        runtime_deps,
        srcs,
        tags,
        tests,
        typing,
        typing_options,
        version_subdirs,
        versioned_srcs,
        visibility):
    """
    Gathers the attributes implicit python_library and creates associated rules

    This is suitable for usage by either python_binary, python_unittest or
    python_library. See `implicit_python_library` for more details

    Returns:
        Attributes for a native.python_library,
    """

    # for binary we need a separate library
    if is_library:
        library_name = name
    else:
        library_name = name + "-library"

    if is_library and check_types:
        fail(
            "parameter `check_types` is not supported for libraries, did you " +
            "mean to specify `typing`?",
        )

    if get_typing_config_target():
        gen_typing_config(
            library_name,
            base_module if base_module != None else base_path,
            srcs,
            [src_and_dep_helpers.convert_build_target(base_path, dep) for dep in deps],
            typing or check_types,
            typing_options,
            visibility,
        )

    if runtime_deps:
        associated_targets_name = _associated_targets_library(
            base_path,
            library_name,
            runtime_deps,
            visibility,
        )
        deps = list(deps) + [":" + associated_targets_name]

    extra_tags = []
    if not is_library:
        extra_tags.append("generated")
    if is_test:
        extra_tags.append("unittest-library")

    return _implicit_python_library(
        library_name,
        is_test_companion = is_test,
        base_module = base_module,
        srcs = srcs,
        versioned_srcs = versioned_srcs,
        gen_srcs = gen_srcs,
        deps = deps,
        tests = tests,
        tags = list(tags) + extra_tags,
        external_deps = external_deps,
        visibility = visibility,
        resources = resources,
        cpp_deps = cpp_deps,
        py_flavor = py_flavor,
        version_subdirs = version_subdirs,
    )

def _single_binary_or_unittest(
        base_path,
        name,
        implicit_library_target,
        implicit_library_attributes,
        fbconfig_rule_type,
        buck_rule_type,
        is_test,
        tests,
        py_version,
        py_flavor,
        main_module,
        strip_libpar,
        tags,
        par_style,
        emails,
        needed_coverage,
        argcomplete,
        strict_tabs,
        compile,
        args,
        env,
        python,
        allocator,
        check_types,
        preload_deps,
        jemalloc_conf,  # TODO: This does not appear to be used anywhere
        typing_options,
        helper_deps,
        visibility,
        analyze_imports,
        additional_coverage_targets,
        generate_test_modules):
    if is_test and par_style == None:
        par_style = "xar"
    dependencies = []
    platform_deps = []
    out_preload_deps = []
    platform = platform_utils.get_platform_for_base_path(base_path)
    python_version = python_versioning.get_default_version(
        platform = platform,
        constraint = py_version,
        flavor = py_flavor,
    )
    if python_version == None:
        fail(
            (
                "Unable to find Python version matching constraint" +
                "'{}' and flavor '{}' on '{}'."
            ).format(py_version, py_flavor, platform),
        )

    python_platform = platform_utils.get_buck_python_platform(
        platform,
        major_version = python_version.major,
        flavor = py_flavor,
    )

    if allocator == None:
        allocator = allocators.normalize_allocator(allocator)

    attributes = {}
    attributes["name"] = name
    if is_test and additional_coverage_targets:
        attributes["additional_coverage_targets"] = additional_coverage_targets
    if visibility != None:
        attributes["visibility"] = visibility

    # If this is a test, we need to merge the library rule into this
    # one and inherit its deps.
    if is_test:
        for param in ("versioned_srcs", "srcs", "resources", "base_module"):
            val = implicit_library_attributes.get(param)
            if val != None:
                attributes[param] = val
        dependencies.extend(implicit_library_attributes.get("deps", []))
        platform_deps.extend(implicit_library_attributes.get("platform_deps", []))

        # Add the "coverage" library as a dependency for all python tests.
        platform_deps.extend(
            src_and_dep_helpers.format_platform_deps(
                [target_utils.ThirdPartyRuleTarget("coverage", "coverage-py")],
            ),
        )

        # Otherwise, this is a binary, so just the library portion as a dep.
    else:
        dependencies.append(":" + implicit_library_attributes["name"])

    # Sanitize the main module, so that it's a proper module reference.
    if main_module != None:
        main_module = main_module.replace("/", ".")
        if main_module.endswith(".py"):
            main_module = main_module[:-3]
        attributes["main_module"] = main_module
    elif is_test:
        main_module = "__fb_test_main__"
        attributes["main_module"] = main_module

    # Add in the PAR build args.
    if _get_package_style() == "standalone":
        build_args = (
            _get_par_build_args(
                base_path,
                name,
                buck_rule_type,
                platform,
                argcomplete = argcomplete,
                strict_tabs = strict_tabs,
                compile = compile,
                par_style = par_style,
                strip_libpar = strip_libpar,
                needed_coverage = needed_coverage,
                python = python,
            )
        )
        if build_args:
            attributes["build_args"] = build_args

    # Add any special preload deps.
    default_preload_deps = (
        _preload_deps(base_path, name, allocator, jemalloc_conf, visibility)
    )
    out_preload_deps.extend(src_and_dep_helpers.format_deps(default_preload_deps))

    # Add user-provided preloaded deps.
    for dep in preload_deps:
        out_preload_deps.append(src_and_dep_helpers.convert_build_target(base_path, dep))

    # Add the C/C++ build info lib to preload deps.
    cxx_build_info = cpp_common.cxx_build_info_rule(
        base_path,
        name,
        fbconfig_rule_type,
        platform,
        static = False,
        visibility = visibility,
    )
    out_preload_deps.append(target_utils.target_to_label(cxx_build_info))

    # Provide a standard set of backport deps to all binaries
    platform_deps.extend(
        src_and_dep_helpers.format_platform_deps(
            [
                target_utils.ThirdPartyRuleTarget("typing", "typing-py"),
                target_utils.ThirdPartyRuleTarget("python-future", "python-future-py"),
            ],
        ),
    )

    # Provide a hook for the nuclide debugger in @mode/dev builds, so
    # that one can have `PYTHONBREAKPOINT=nuclide.set_trace` in their
    # environment (eg .bashrc) and then simply write `breakpoint()`
    # to launch a debugger with no fuss
    if _get_package_style() == "inplace":
        dependencies.append("//nuclide:debugger-hook")

    # Add in a specialized manifest when building inplace binaries.
    #
    # TODO(#11765906):  We shouldn't need to create this manifest rule for
    # standalone binaries.  However, since target determinator runs in dev
    # mode, we sometimes pass these manifest targets in the explicit target
    # list into `opt` builds, which then fails with a missing build target
    # error.  So, for now, just always generate the manifest library, but
    # only use it when building inplace binaries.
    manifest_name = _manifest_library(
        base_path,
        name,
        fbconfig_rule_type,
        main_module,
        platform,
        python_platform,
        visibility,
    )
    if _get_package_style() == "inplace":
        dependencies.append(":" + manifest_name)

    buck_cxx_platform = platform_utils.get_buck_platform_for_base_path(base_path)
    attributes["cxx_platform"] = buck_cxx_platform
    attributes["platform"] = python_platform
    attributes["version_universe"] = _get_version_universe(python_version)
    attributes["linker_flags"] = (
        _get_ldflags(base_path, name, fbconfig_rule_type, strip_libpar = strip_libpar)
    )

    attributes["labels"] = list(tags)
    if is_test:
        attributes["labels"].extend(label_utils.convert_labels(platform, "python"))

    attributes["tests"] = tests

    if args:
        attributes["args"] = (
            string_macros.convert_args_with_macros(
                base_path,
                args,
                platform = platform,
            )
        )

    if env:
        attributes["env"] = (
            string_macros.convert_env_with_macros(
                env,
                platform = platform,
            )
        )

    if emails:
        attributes["contacts"] = emails

    if out_preload_deps:
        attributes["preload_deps"] = out_preload_deps

    if needed_coverage:
        attributes["needed_coverage"] = [
            _convert_needed_coverage_spec(base_path, s)
            for s in needed_coverage
        ]

    # Generate the interpreter helpers, and add them to our deps. Note that
    # we must do this last, so that the interp rules get the same deps as
    # the main binary which we've built up to this point.
    # We also do this based on an attribute so that we don't have to dedupe
    # rule creation. We'll revisit this in the near future.
    # TODO: Better way to not generate duplicates
    if _should_generate_interp_rules(helper_deps):
        interp_deps = list(dependencies)
        if is_test:
            testmodules_library_name = _test_modules_library(
                base_path,
                implicit_library_attributes["name"],
                implicit_library_attributes.get("srcs") or (),
                implicit_library_attributes.get("base_module"),
                visibility,
                generate_test_modules = generate_test_modules,
            )
            interp_deps.append(":" + testmodules_library_name)
        interp_rules = _interpreter_binaries(
            name,
            buck_cxx_platform,
            python_version,
            python_platform,
            interp_deps,
            platform_deps,
            out_preload_deps,
            visibility,
        )
        dependencies.extend([":" + interp_rule for interp_rule in interp_rules])
    if check_types:
        if python_version.major != 3:
            fail("parameter `check_types` is only supported on Python 3.")
        typecheck_rule_name = _typecheck_test(
            name,
            main_module,
            buck_cxx_platform,
            python_platform,
            python_version,
            dependencies,
            platform_deps,
            out_preload_deps,
            typing_options,
            visibility,
            emails,
            implicit_library_target,
            implicit_library_attributes.get("versioned_srcs"),
            implicit_library_attributes.get("srcs"),
            implicit_library_attributes.get("resources"),
            implicit_library_attributes.get("base_module"),
        )
        attributes["tests"] = (
            list(attributes["tests"]) + [":" + typecheck_rule_name]
        )
    if analyze_imports:
        _analyze_import_binary(
            name,
            buck_cxx_platform,
            python_platform,
            python_version,
            dependencies,
            platform_deps,
            out_preload_deps,
            visibility,
        )
    if is_test:
        if not dependencies:
            dependencies = []
        dependencies.append("//python:fbtestmain")

    if dependencies:
        attributes["deps"] = dependencies

    if platform_deps:
        attributes["platform_deps"] = platform_deps

    if (
        read_bool("fbcode", "monkeytype", False) and
        python_version.major == 3
    ):
        _monkeytype_binary(buck_rule_type, attributes, implicit_library_attributes["name"])

    return attributes

def _convert_binary(
        is_test,
        fbconfig_rule_type,
        buck_rule_type,
        base_path,
        name,
        py_version,
        py_flavor,
        base_module,
        main_module,
        strip_libpar,
        srcs,
        versioned_srcs,
        tags,
        gen_srcs,
        deps,
        tests,
        par_style,
        emails,
        external_deps,
        needed_coverage,
        argcomplete,
        strict_tabs,
        compile,
        args,
        env,
        python,
        allocator,
        check_types,
        preload_deps,
        visibility,
        resources,
        jemalloc_conf,
        typing,
        typing_options,
        check_types_options,
        runtime_deps,
        cpp_deps,
        helper_deps,
        analyze_imports,
        additional_coverage_targets,
        version_subdirs):
    """
    Generate binary rules and library rules for a python_binary or python_unittest

    Returns:
        A list of kwargs for all unittests/binaries that need to be created
    """

    library_attributes = python_common.convert_library(
        is_test = is_test,
        is_library = False,
        base_path = base_path,
        name = name,
        base_module = base_module,
        check_types = check_types,
        cpp_deps = cpp_deps,
        deps = deps,
        external_deps = external_deps,
        gen_srcs = gen_srcs,
        py_flavor = py_flavor,
        resources = resources,
        runtime_deps = runtime_deps,
        srcs = srcs,
        tags = tags,
        tests = tests,
        typing = typing,
        typing_options = typing_options,
        version_subdirs = version_subdirs,
        versioned_srcs = versioned_srcs,
        visibility = visibility,
    )

    # People use -library of unittests
    fb_native.python_library(**library_attributes)

    # For binary rules, create a separate library containing the sources.
    # This will be added as a dep for python binaries and merged in for
    # python tests.
    if is_list(py_version) and len(py_version) == 1:
        py_version = py_version[0]

    if not is_list(py_version):
        versions = {py_version: name}
    else:
        versions = {}
        platform = platform_utils.get_platform_for_base_path(base_path)
        for py_ver in py_version:
            python_version = python_versioning.get_default_version(platform, py_ver)
            new_name = name + "-" + python_version.version_string
            versions[py_ver] = new_name

    # There are some sub-libraries that get generated based on the
    # name of the original library, not the binary. Make sure they're only
    # generated once.
    is_first_binary = True
    all_binary_attributes = []
    for py_ver, py_name in sorted(versions.items()):
        # Turn off check types for py2 targets when py3 is in versions
        # so we can have the py3 parts type check without a separate target
        if (
            check_types and
            python_versioning.constraint_matches_major(py_ver, version = 2) and
            any([
                python_versioning.constraint_matches_major(v, version = 3)
                for v in versions
            ])
        ):
            _check_types = False
            print(
                base_path + ":" + py_name,
                "will not be typechecked because it is the python 2 part",
            )
        else:
            _check_types = check_types

        binary_attributes = _single_binary_or_unittest(
            base_path,
            py_name,
            implicit_library_target = ":" + library_attributes["name"],
            implicit_library_attributes = library_attributes,
            fbconfig_rule_type = fbconfig_rule_type,
            buck_rule_type = buck_rule_type,
            is_test = is_test,
            tests = tests,
            py_version = py_ver,
            py_flavor = py_flavor,
            main_module = main_module,
            strip_libpar = strip_libpar,
            tags = tags,
            par_style = par_style,
            emails = emails,
            needed_coverage = needed_coverage,
            argcomplete = argcomplete,
            strict_tabs = strict_tabs,
            compile = compile,
            args = args,
            env = env,
            python = python,
            allocator = allocator,
            check_types = _check_types,
            preload_deps = preload_deps,
            jemalloc_conf = jemalloc_conf,
            typing_options = check_types_options,
            helper_deps = helper_deps,
            visibility = visibility,
            analyze_imports = analyze_imports,
            additional_coverage_targets = additional_coverage_targets,
            generate_test_modules = is_first_binary,
        )
        is_first_binary = False
        all_binary_attributes.append(binary_attributes)

    return all_binary_attributes

python_common = struct(
    analyze_import_binary = _analyze_import_binary,
    associated_targets_library = _associated_targets_library,
    convert_binary = _convert_binary,
    convert_library = _convert_library,
    convert_needed_coverage_spec = _convert_needed_coverage_spec,
    file_to_python_module = _file_to_python_module,
    get_ldflags = _get_ldflags,
    get_package_style = _get_package_style,
    get_build_info = _get_build_info,
    get_interpreter_for_platform = _get_interpreter_for_platform,
    get_par_build_args = _get_par_build_args,
    get_version_universe = _get_version_universe,
    implicit_python_library = _implicit_python_library,
    interpreter_binaries = _interpreter_binaries,
    jemalloc_malloc_conf_library = _jemalloc_malloc_conf_library,
    manifest_library = _manifest_library,
    monkeytype_binary = _monkeytype_binary,
    parse_gen_srcs = _parse_gen_srcs,
    parse_srcs = _parse_srcs,
    preload_deps = _preload_deps,
    single_binary_or_unittest = _single_binary_or_unittest,
    should_generate_interp_rules = _should_generate_interp_rules,
    test_modules_library = _test_modules_library,
    typecheck_test = _typecheck_test,
)
