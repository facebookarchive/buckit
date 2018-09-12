# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import functools
import pkg_resources
import copy
import collections
import subprocess
import os
import tempfile
import shutil
import logging
import platform
import re
import stat
import StringIO
import textwrap
import unittest

import six
from future.utils import raise_with_traceback

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

RunResult = collections.namedtuple(
    "RunResult", ["returncode", "stdout", "stderr"]
)
UnitTestResult = collections.namedtuple(
    "UnitTestResult", ["returncode", "stdout", "stderr", "debug_lines"]
)
AuditTestResult = collections.namedtuple(
    "AuditTestResult", ["returncode", "stdout", "stderr", "files"]
)


def dedent(text):
    return textwrap.dedent(text).strip()


def __recursively_get_files_contents(base):
    """
    Recursively get all file contents for a given path from pkg_resources

    Arguments:
        base: The subdirectory to look in first. Use '' for the root
    Returns:
        Map of relative path to a string of the file's contents
    """
    is_file = (
        pkg_resources.resource_exists(__name__, base) and
        not pkg_resources.resource_isdir(__name__, base)
    )
    if is_file:
        return {base: pkg_resources.resource_string(__name__, base)}

    ret = {}
    for file in pkg_resources.resource_listdir(__name__, base):
        full_path = os.path.join(base, file)
        if not pkg_resources.resource_isdir(__name__, full_path):
            ret[full_path] = pkg_resources.resource_string(__name__, full_path)
        else:
            ret.update(__recursively_get_files_contents(full_path))
    return ret


def recursively_get_files_contents(base, strip_base):
    """
    Recursively get all file contents for a given path from pkg_resources

    Arguments:
        base: The subdirectory to look in first. Use '' for the root
        strip_base: If true, strip 'base' from the start of all paths that are
                    returned
    Returns:
        Map of relative path to a string of the file's contents
    """
    ret = __recursively_get_files_contents(base)
    if strip_base:
        # + 1 is for the /
        ret = {path[len(base) + 1:]: ret[path] for path in ret.keys()}
    return ret


class Cell:
    """
    Represents a repository. Files, .buckconfig, and running commands are all
    done in this class
    """

    def __init__(self, name, project):
        self.name = name
        self.buckconfig = collections.defaultdict(dict)
        self.buckconfig["ui"]["superconsole"] = "disabled"
        self.buckconfig["color"]["ui"] = "false"
        self.project = project
        self._directories = []
        self._files = recursively_get_files_contents(name, True)
        self._helper_functions = []
        self._executable_files = set()

    def addFile(self, relative_path, contents, executable=False):
        """
        Add a file that should be written into this cell when running commands
        """
        self._files[relative_path] = contents
        if executable:
            self._executable_files.add(relative_path)

    def addResourcesFrom(self, relative_path):
        """
        Add a file or directory from pkg_resources to this cell
        """
        files = recursively_get_files_contents(relative_path, False)
        self._files.update(files)
        return files

    def addDirectory(self, relative_path):
        """
        Add an empty directory in this cell that will be created when commmands
        are run
        """
        self._directories.append(relative_path)

    def fullPath(self):
        """
        Get the full path to this cell's root
        """
        return os.path.join(self.project.project_path, self.name)

    def updateBuckconfig(self, section, key, value):
        """
        Update the .buckconfig for this cell
        """
        self.buckconfig[section][key] = value

    def updateBuckconfigWithDict(self, values):
        """
        Update the .buckconfig for this cell with multiple values

        Arguments:
            values: A dictionary of dictionaries. The top level key is the
                    section. Second level dictionaries are mappings of fields
                    to values. .buckconfig is merged with 'values' taking
                    precedence
        """
        for section, kvps in values.items():
            for key, value in kvps.items():
                self.buckconfig[section][key] = value

    def createBuckconfigContents(self):
        """
        Create contents of a .buckconfig file
        """
        buckconfig = copy.deepcopy(self.buckconfig)
        for cell_name, cell in self.project.cells.items():
            relative_path = os.path.relpath(cell.fullPath(), self.fullPath())
            buckconfig["repositories"][cell_name] = relative_path
        if "polyglot_parsing_enabled" not in buckconfig["parser"]:
            buckconfig["parser"]["polyglot_parsing_enabled"] = "true"
        if "default_build_file_syntax" not in buckconfig["parser"]:
            buckconfig["parser"]["default_build_file_syntax"] = "SKYLARK"
        if "cxx" not in buckconfig or "cxx" not in buckconfig["cxx"]:
            cxx = self._findCXX()
            cc = self._findCC()
            if cxx:
                buckconfig["cxx"]["cxx"] = cxx
                buckconfig["cxx"]["cxxpp"] = cxx
                buckconfig["cxx"]["ld"] = cxx
            if cc:
                buckconfig["cxx"]["cc"] = cc
                buckconfig["cxx"]["cpp"] = cc
                buckconfig["cxx"]["aspp"] = cc
        if ("fbcode" not in buckconfig or
                "buck_platform_format" not in buckconfig["fbcode"]):
            buckconfig["fbcode"]["buck_platform_format"] = "{platform}-{compiler}"

        parser = configparser.ConfigParser()
        for section, kvps in buckconfig.items():
            if len(kvps):
                parser.add_section(section)
                for key, value in kvps.items():
                    if isinstance(value, list):
                        value = ",".join(value)
                    parser.set(section, key, str(value))
        writer = StringIO.StringIO()
        try:
            parser.write(writer)
            return writer.getvalue()
        finally:
            writer.close()

    def _findCC(self):
        for path_component in os.environ.get("PATH").split(os.pathsep):
            for bin in ("gcc.par", "gcc"):
                full_path = os.path.join(path_component, bin)
                if os.path.exists(full_path):
                    return full_path
        return None

    def _findCXX(self):
        for path_component in os.environ.get("PATH").split(os.pathsep):
            for bin in ("g++.par", "g++"):
                full_path = os.path.join(path_component, bin)
                if os.path.exists(full_path):
                    return full_path
        return None

    def setupFilesystem(self):
        """
        Sets up the filesystem for this cell in self.fullPath()

        This method:
        - creates all directories
        - creates all specified files and their parent directories
        - writes out a .buckconfig file
        """
        cell_path = self.fullPath()

        if not os.path.exists(cell_path):
            os.makedirs(cell_path)

        for directory in self._directories:
            dir_path = os.path.join(cell_path, directory)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

        for path, contents in self._files.items():
            self.writeFile(path, contents, executable=path in self._executable_files)

        buckconfig = self.createBuckconfigContents()
        with open(os.path.join(cell_path, ".buckconfig"), "w") as fout:
            fout.write(buckconfig)

    def setupAllFilesystems(self):
        """
        Sets up the filesystem per self.setupFilesystem for this cell and
        all others
        """
        for cell in self.project.cells.values():
            cell.setupFilesystem()

    def writeFile(self, relative_path, contents, executable=False):
        """
        Writes out a file into the cell, making parent dirs if necessary
        """
        cell_path = self.fullPath()
        dir_path, filename = os.path.split(relative_path)
        full_dir_path = os.path.join(cell_path, dir_path)
        file_path = os.path.join(cell_path, relative_path)
        if dir_path and not os.path.exists(full_dir_path):
            os.makedirs(full_dir_path)
        with open(file_path, "w") as fout:
            fout.write(contents)
        if executable:
            os.chmod(file_path, os.stat(file_path).st_mode | stat.S_IEXEC)

    def getDefaultEnvironment(self):
        # We don't start a daemon up because:
        # - Generally we're only running once, and in a temp dir, so it doesn't
        #   make a big difference
        # - We want to make sure things cleanup properly, and this is just
        #   easier
        ret = dict(os.environ)
        if not self.project.run_buckd:
            ret["NO_BUCKD"] = "1"
        elif "NO_BUCKD" in ret:
            del ret["NO_BUCKD"]
        return ret

    def run(self, cmd, extra_files, environment_overrides):
        """
        Runs a command

        Arguments:
            cmd: A list of arguments that comprise the command to be run
            extra_files: A dictionary of relative path: contents that should be
                         written after the rest of the files are written out
            environment_overrides: A dictionary of extra environment variables
                                   that should be set
        Returns:
            The RunResult from running the command
        """
        self.setupAllFilesystems()
        for path, contents in extra_files.items():
            self.writeFile(path, contents)
        environment = self.getDefaultEnvironment()
        environment.update(environment_overrides or {})
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.fullPath(),
            env=environment,
        )
        stdout, stderr = proc.communicate()
        return RunResult(proc.returncode, stdout, stderr)

    def _parseAuditOutput(self, stdout, files):
        ret = {file: None for file in files}
        current_file = None
        file_contents = ""
        for line in stdout.splitlines():
            if line.startswith("#"):
                found_filename = line.strip("# ")
                if found_filename in ret:
                    if current_file is not None:
                        ret[current_file] = file_contents.strip()
                    current_file = found_filename
                    file_contents = ""
                    continue
            if found_filename is None and line:
                raise Exception(
                    (
                        "Got line, but no filename has been found so far.\n"
                        "Line: {}\n"
                        "stdout:\n{}"
                    ).format(line, stdout)
                )
            file_contents += line + "\n"
        ret[current_file] = file_contents.strip()
        return ret

    def runAudit(self, buck_files, environment=None):
        """
        A method to compare existing outputs of `buck audit rules` to new ones
        and ensure that the final product works as expected

        Arguments:
            buck_files: A list of relative paths to buck files that should have
                        `buck audit rules` run on them.
        Returns:
            An AuditTestResult object, with returncode, stdout, stderr filled
            out, and files set as a dictionary of files names -> trimmed
            content returned from buck audit rules
        """
        default_env = {}
        if not self.project.run_buckd:
            default_env["NO_BUCKD"] = "1"
        environment = default_env.update(environment or {})

        cmd = ["buck", "audit", "rules"] + buck_files

        ret = self.run(cmd, {}, environment)
        audit_files = self._parseAuditOutput(ret.stdout, buck_files)

        return AuditTestResult(
            returncode=ret.returncode,
            stdout=ret.stdout,
            stderr=ret.stderr,
            files=audit_files
        )

    def runUnitTests(
        self,
        includes,
        statements,
        extra_declarations=None,
        environment_overrides=None,
        buckfile="BUCK",
    ):
        """
        Evaluate a series of statements, parse their repr from buck, and
        return reconsituted objects, along with the results of buck audit rules
        on an auto-generated file

        Arguments:
            includes: A list of tuples to be used in a `load()` statement. The
                      first element should be the .bzl file to be included.
                      Subsequent elements are variables that should be loaded
                      from the .bzl file. (e.g. `("//:test.bzl", "my_func")`)
            statements: A list of statements that should be evaluated. This
                        is usually just a list of function calls. This can
                        reference things specified in `extra_declarations`.
                        e.g. after importing a "config" struct:
                            [
                                "config.foo",
                                "config.bar(1, 2, {"baz": "string"})"
                            ]
                        would run each of those statements.
            extra_declarations: If provided, a list of extra code that should
                                go at the top of the generated BUCK file. This
                                isn't normally needed, but if common data
                                objects are desired for use in multiple
                                statments, it can be handy
            environment_overrides: If provided, the environment to merge over
                                   the top of the generated environment when
                                   executing buck. If not provided, then a
                                   generated environment is used.
            buckfile: The name of the temporary buckfile to write
        Returns:
            A UnitTestResult object that contains the returncode, stdout,
            stderr, of buck audit rules, as well as any deserialized objects
            from evaluating statements. If the file could be parsed properly
            and buck returns successfully, debug_lines will contain the objects
            in the same order as 'statements'
        """

        # We don't start a daemon up because:
        # - Generally we're only running once, and in a temp dir, so it doesn't
        #   make a big difference
        # - We want to make sure things cleanup properly, and this is just
        #   easier
        buck_file_content = ""

        if len(statements) == 0:
            raise ValueError("At least one statement must be provided")

        for include in includes:
            if len(include) < 2:
                raise ValueError(
                    "include ({}) must have at least two elements: a path to "
                    "include, and at least one var to import".format(include)
                )

            vars = ",".join(('"' + var + '"' for var in include[1:]))
            buck_file_content += 'load("{}", {})\n'.format(include[0], vars)
        buck_file_content += extra_declarations or ""
        buck_file_content += "\n"
        for statement in statements:
            buck_file_content += (
                'print("TEST_RESULT: %s" % repr({}))\n'.format(statement)
            )

        cmd = ["buck", "audit", "rules", buckfile]
        result = self.run(
            cmd, {buckfile: buck_file_content}, environment_overrides
        )
        debug_lines = []
        for line in result.stderr.split("\n"):
            # python. Sample line: | TEST_RESULT: {}
            if line.startswith("| TEST_RESULT:"):
                debug_lines.append(
                    self._convertDebug(line.split(":", 1)[-1].strip()))
            # Sample line: DEBUG: /Users/user/temp/BUCK:1:1: TEST_RESULT: "hi"
            elif line.startswith("DEBUG: ") and "TEST_RESULT:" in line:
                debug_lines.append(
                    self._convertDebug(line.split(":", 5)[-1].strip()))
        return UnitTestResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            debug_lines=debug_lines,
        )

    def _convertDebug(self, string):
        """
        Converts a TEST_RESULT line generated by run_unittests into a real
        object. Functions are turned into 'function' named tuples, and structs
        are also turned into a namedtuple
        """

        def struct(**kwargs):
            return collections.namedtuple("struct",
                                          sorted(kwargs.keys()))(**kwargs)

        def function(name):
            return collections.namedtuple("function", ["name"])(name)

        string = re.sub(r'<function (\w+)>', r'function("\1")', string)
        # Yup, eval.... this lets us have nested struct objects easily so we
        # can do stricter type checking
        return eval(
            string, {
                "__builtins__":
                    {
                        "struct": struct,
                        "function": function,
                        "True": True,
                        "False": False,
                    }
            }, {}
        )


class Project:
    """
    An object that represents all cells for a run, and handles creating and
    cleaning up the temp directory that we work in
    """

    def __init__(
        self,
        remove_files=None,
        add_fbcode_macros_cell=True,
        add_skylib_cell=True,
        run_buckd=False
    ):
        """
        Create an instance of Project

        Arguments:
            remove_files: Whether files should be removed when __exit__ is
                          called
            add_fbcode_macros_cell: Whether to create the fbcode_macros cell
                                    when __enter__ is called
            add_skylib_cell: Whether to create the skylib cell when __enter__
                             is called
        """

        if remove_files is None:
            remove_files = os.environ.get('FBCODE_MACROS_KEEP_DIRS') != '1'

        self.root_cell = None
        self.project_path = None
        self.remove_files = remove_files
        self.add_fbcode_macros_cell = add_fbcode_macros_cell
        self.add_skylib_cell = add_skylib_cell
        self.cells = {}
        self.run_buckd = run_buckd

    def __enter__(self):
        self.project_path = tempfile.mkdtemp()
        self.root_cell = self.addCell("root")
        self.root_cell.addResourcesFrom(".buckversion")

        if self.add_fbcode_macros_cell:
            self.addCell("fbcode_macros")
        if self.add_skylib_cell:
            self.addCell("bazel_skylib")
        return self

    def __exit__(self, type, value, traceback):
        self.killBuckd()
        if self.project_path:
            if self.remove_files:
                shutil.rmtree(self.project_path)
            else:
                logging.info(
                    "Not deleting temporary files at {}".format(
                        self.project_path
                    )
                )

    def killBuckd(self):
        for cell in self.cells.values():
            cell_path = cell.fullPath()
            if os.path.exists(os.path.join(cell_path, ".buckd")):
                try:
                    with open(os.devnull, "w") as dev_null:
                        subprocess.check_call(
                            ["buck", "kill"],
                            stdout=dev_null,
                            stderr=dev_null,
                            cwd=cell_path,
                        )
                except subprocess.CalledProcessError as e:
                    print("buck kill failed: {}".format(e))

    def addCell(self, name):
        """Add a new cell"""
        if name in self.cells:
            raise ValueError("Cell {} already exists".format(name))
        new_cell = Cell(name, self)
        self.cells[name] = new_cell
        return new_cell


def with_project(
    use_skylark=True, use_python=True, *project_args, **project_kwargs
):
    """
    Annotation that makes a project available to a test. This passes the root
    cell to the function being annotated and tears down the temporary
    directory (by default, can be overridden) when the method finishes executing
    """

    if not use_python and not use_skylark:
        raise ValueError("Either use_python or use_skylark must be set")

    def wrapper(f):
        suffixes = getattr(f, "_function_suffixes", set())
        if use_skylark:
            suffixes.add("skylark")
        if use_python:
            suffixes.add("python")
        if suffixes:
            setattr(f, "_function_suffixes", suffixes)

        @functools.wraps(f)
        def inner_wrapper(suffix, *args, **kwargs):
            if suffix == "skylark":
                build_file_syntax = "SKYLARK"
            elif suffix == "python":
                build_file_syntax = "PYTHON_DSL"
            else:
                raise ValueError("Unknown parser type: %s" % suffix)

            with Project(*project_args, **project_kwargs) as project:
                new_args = args + (project.root_cell, )
                if isinstance(new_args[0], TestCase):
                    new_args[0].setUpProject(project.root_cell)
                project.root_cell.updateBuckconfig(
                    "parser", "default_build_file_syntax", build_file_syntax
                )
                f(*new_args, **kwargs)

        return inner_wrapper

    return wrapper


class TestMethodRenamer(type):
    """
    Simple metaclass class that renames test_foo to test_foo_skylark and
    test_foo_python
    """

    def __new__(metacls, name_, bases, classdict):
        bases = bases or []

        newclassdict = {}
        for name, attr in classdict.items():
            suffixes = getattr(attr, "_function_suffixes", None)
            if callable(attr) and suffixes:
                for suffix in suffixes:
                    new_name = str(name + "_" + suffix)
                    assert new_name not in newclassdict

                    # The extra lambda is so that things get bound properly.
                    def call_with_suffix(s=suffix, a=attr):
                        def inner(*args, **kwargs):
                            return a(s, *args, **kwargs)

                        inner.__name__ = new_name
                        return inner

                    newclassdict[new_name] = call_with_suffix()
            else:
                newclassdict[name] = attr
        return type.__new__(metacls, name_, bases, newclassdict)


@six.add_metaclass(TestMethodRenamer)
class TestCase(unittest.TestCase):
    maxDiff = None
    setupPathsConfig = True
    setupThirdPartyConfig = True
    setupPlatformOverrides = True
    setupBuildOverrides = True
    setupCoreToolsTargets = True

    def setUpProject(self, root):
        # Setup some defaults for the environment
        if self.setupPathsConfig:
            self.addPathsConfig(root)
        if self.setupThirdPartyConfig:
            self.addDummyThirdPartyConfig(root)
        if self.setupPlatformOverrides:
            self.addDummyPlatformOverrides(root)
        if self.setupBuildOverrides:
            self.addDummyBuildModeOverrides(root)
        if self.setupCoreToolsTargets:
            self.addDummyCoreToolsTargets(root)

    def addDummyCoreToolsTargets(self, root):
        root.project.cells["fbcode_macros"].writeFile(
            "build_defs/core_tools_targets.bzl",
            dedent(
                """
                load("@bazel_skylib//lib:new_sets.bzl", "sets")
                core_tools_targets = sets.make([])
                """))

    def addDummyThirdPartyConfig(self, root):
        current_arch = platform.machine()
        other_arch = "x86_64" if current_arch == "aarch64" else "aarch64"
        third_party_config = dedent(
            """\
            third_party_config = {{
                "platforms": {{
                    "gcc5": {{
                        "architecture": "{current_arch}",
                        "tools": {{}},
                    }},
                    "gcc6": {{
                        "architecture": "{current_arch}",
                        "tools": {{}},
                    }},
                    "gcc7": {{
                        "architecture": "{current_arch}",
                        "tools": {{}},
                    }},
                    "gcc5-other": {{
                        "architecture": "{other_arch}",
                        "tools": {{}},
                    }},
                    "default": {{
                        "architecture": "{current_arch}",
                        "tools": {{}},
                    }},
                }},
            }}
        """.format(current_arch=current_arch, other_arch=other_arch)
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/third_party_config.bzl", third_party_config
        )

    def addDummyPlatformOverrides(self, root):
        platform_overrides = dedent(
            """\
            platform_overrides = {
                "fbcode": {
                    "foo/bar": ["gcc5", "gcc5-other"],
                    "foo": ["gcc7"],
                },
            }
            """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/platform_overrides.bzl", platform_overrides
        )

    def addDummyBuildModeOverrides(self, root):
        build_mode_overrides = dedent(
            """
            load(
                "@fbcode_macros//build_defs:create_build_mode.bzl",
                "create_build_mode",
            )
            def dev():
                return {
                    "dev": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def dbg():
                return {
                    "dbg": create_build_mode(c_flags=["-DDEBUG"]),
                }
            def opt():
                return {
                    "opt": create_build_mode(c_flags=["-DDEBUG"]),
                }
            build_mode_overrides = {"fbcode": {
                "foo/bar": dev,
                "foo/bar-other": dbg,
                "foo": opt,
            }}
        """
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/build_mode_overrides.bzl", build_mode_overrides
        )

    def addPathsConfig(
        self,
        root,
        third_party_root="third-party-buck",
        use_platforms_and_build_subdirs=True
    ):
        paths_config = dedent(
            """
            paths_config = struct(
                third_party_root="%s",
                use_platforms_and_build_subdirs=%r,
            )
            """ % (third_party_root, use_platforms_and_build_subdirs)
        )
        root.project.cells["fbcode_macros"].addFile(
            "build_defs/paths_config.bzl", paths_config
        )

    def assertSuccess(self, result, *expected_results):
        """ Make sure that the command ran successfully """
        self.assertEqual(
            0, result.returncode,
            "Expected zero return code\nSTDOUT:\n{}\nSTDERR:\n{}\n".format(
                result.stdout, result.stderr
            )
        )
        if expected_results:
            self.assertEqual(list(expected_results), result.debug_lines)

    def assertFailureWithMessage(
        self, result, expected_message, *other_messages
    ):
        """ Make sure that we failed with a substring in stderr """
        self.assertNotEqual(0, result.returncode)
        try:
            self.assertIn(expected_message, result.stderr)
        except AssertionError as e:
            # If we get a parse error, it's a lot easier to read as multiple
            # lines, rather than a single line witn \n in it
            e.args = (e.args[0].replace(r'\n', '\n'),) + e.args[1:]
            raise e
        for message in expected_message:
            self.assertIn(message, result.stderr)

    def validateAudit(self, expected_results, result):
        """
        Validate that audit results are as expected

        Validates that all requested files came out in the audit comment. Also
        validates that the command ran successfully, and that the contents
        are as expected

        Arguments:
            expected_results: A dictionary of file name to contents
            result: An AuditTestResult object
        """
        self.assertSuccess(result)
        empty_results = [
            file for file, contents in result.files.items() if contents is None
        ]
        try:
            self.assertEqual([], empty_results)
        except AssertionError as e:
            raise_with_traceback(
                AssertionError(
                    "Got a list of files that had empty contents: {!r}\n{}".
                    format(empty_results, str(e))
                )
            )

        try:
            self.assertEqual(
                sorted(expected_results.keys()),
                sorted(result.files.keys()))
        except AssertionError as e:
            raise_with_traceback(
                AssertionError(
                    "Parsed list of files != expected list of files:\n{}".
                    format(str(e))
                )
            )

        for file, contents in result.files.items():
            try:
                self.assertEqual(expected_results[file], contents)
            except AssertionError as e:
                raise_with_traceback(
                    AssertionError(
                        "Content of {} differs:\n{}".format(file, str(e))
                    )
                )

    def struct(self, **kwargs):
        """
        Creates a namedtuple that can be compared to 'struct' objects that
        are parsed in unittests
        """
        return collections.namedtuple("struct", sorted(kwargs.keys()))(**kwargs)
