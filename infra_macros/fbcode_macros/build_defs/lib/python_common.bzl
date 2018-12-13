load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:build_info.bzl", "build_info")
load("@fbcode_macros//build_defs/lib:python_typing.bzl", "get_typing_config_target")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:coverage.bzl", "coverage")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_dict")

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
    if is_dict(srcs):
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

python_common = struct(
    analyze_import_binary = _analyze_import_binary,
    file_to_python_module = _file_to_python_module,
    get_build_info = _get_build_info,
    get_interpreter_for_platform = _get_interpreter_for_platform,
    get_par_build_args = _get_par_build_args,
    get_version_universe = _get_version_universe,
    interpreter_binaries = _interpreter_binaries,
    manifest_library = _manifest_library,
    monkeytype_binary = _monkeytype_binary,
    parse_gen_srcs = _parse_gen_srcs,
    parse_srcs = _parse_srcs,
    test_modules_library = _test_modules_library,
    typecheck_test = _typecheck_test,
)
