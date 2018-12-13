load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:build_info.bzl", "build_info")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

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

python_common = struct(
    get_build_info = _get_build_info,
    manifest_library = _manifest_library,
    get_interpreter_for_platform = _get_interpreter_for_platform,
    get_version_universe = _get_version_universe,
    interpreter_binaries = _interpreter_binaries,
)
