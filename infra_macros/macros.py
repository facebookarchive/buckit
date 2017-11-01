#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

# Since this is used as a Buck build def file, we can't normal linting
# as we'll get complaints about magic definitions like `get_base_path()`.
# @lint-avoid-pyflakes2
# @lint-avoid-pyflakes3
# @lint-avoid-python-3-compatibility-imports

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import functools
import itertools
import pipes

with allow_unsafe_import():
    import warnings
    warnings.simplefilter("ignore", ImportWarning)
    warnings.simplefilter("ignore", DeprecationWarning)
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import os
    import pkgutil
    import sys
    import textwrap


# ATTENTION: The buckification macro library is now loaded directly from source
# so there is no deployment process and no need for the version below.
# TODO(#11019082): remove this comment.
# BUCKIFY_PAR_VERSION = 176

# For the time being, error out when the user attempts to use the old mechanism
# for testing the macro library.
if read_config('buildfiles', 'local') is not None:
    msg = """\
the buckification macro library is now used directly from source, so there is
no need to build the PAR or use `-c buildfiles.local=1` for testing."""
    msg = os.linesep.join(textwrap.wrap(msg, 79, subsequent_indent='  '))
    raise Exception(msg)


def find_cell_root(start_path):
    # Keep going up until we find a .buckconfig file
    path = os.path.split(start_path)[0]
    path_terminal = os.path.splitdrive(path)[0] or '/'

    add_build_file_dep('//.buckconfig')
    while path != path_terminal:
        if os.path.exists(os.path.join(path, '.buckconfig')):
            return path
        path = os.path.split(path)[0]
    raise Exception(
        "Could not find .buckconfig in a directory above {}".format(start_path))


macros_py_dir = os.path.dirname(__file__)
CELL_ROOT = find_cell_root(macros_py_dir)
MACRO_LIB_DIR = os.path.join(macros_py_dir, 'macro_lib')

# We're allowed to do absolute paths in add_build_file_dep and include_defs
# so we do. This helps with problems that arise from relative paths when you
# have sibling cells. e.g. below, before, macros// would determine that the
# root was at /, even if we were including the macros defs from cell1//
# Example layout that this helps with:
# /.buckconfig
#  includes = macros//macros.py
# /cell1/.buckconfig
#  includes = macros//macros.py
# /macros/.buckconfig
# /macros/macros.py
include_defs('//{}/config.py'.format(MACRO_LIB_DIR), 'config')


class Loader(object):
    """
    Custom loader to record used sources from the macro library.
    """

    def __init__(self, loader):
        self._loader = loader

    def load_module(self, fullname):
        """
        Intercept imports of macro library modules, and record they're
        inclusion via `include_defs`.
        """

        mod = self._loader.load_module(fullname)
        if mod.__file__.startswith(MACRO_LIB_DIR + os.sep):
            # This is an absolute path
            base_name = os.path.splitext(mod.__file__)[0]
            add_build_file_dep('//' + base_name + '.py')
        return mod


class Finder(pkgutil.ImpImporter):

    def find_module(self, fullname, path=None):
        loader = pkgutil.ImpImporter.find_module(self, fullname, path=path)
        if loader is not None:
            return Loader(loader)


# Add the macro root to the include path and the above import hook to intercept
# and record imports of the macro library.
sys.path_hooks.append(Finder)
sys.path.insert(0, os.path.dirname(MACRO_LIB_DIR))

# Import parts of the macro lib package we'll be using.
include_defs('//{}/converter.py'.format(MACRO_LIB_DIR), 'converter')
include_defs('//{}/constants.py'.format(MACRO_LIB_DIR), 'constants')
include_defs('//{}/BuildMode.py'.format(MACRO_LIB_DIR), 'BuildMode')
include_defs('//{}/global_defns.py'.format(MACRO_LIB_DIR), 'global_defns')
include_defs('//{}/cxx_sources.py'.format(MACRO_LIB_DIR), 'cxx_sources')
include_defs('//{}/rule.py'.format(MACRO_LIB_DIR), 'rule_mod')
include_defs('//{}/convert/base.py'.format(MACRO_LIB_DIR), 'base')
include_defs('//{}/convert/cpp.py'.format(MACRO_LIB_DIR), 'cpp')

# Now that the imports are done, remove the macro lib dir from the path and the
# finder from the path hooks.
del sys.path[0]
sys.path_hooks.pop()

__all__ = []

EXTERNAL_LIBRARY_OVERRIDE = collections.defaultdict(list)
if read_config('tp2', 'override'):
    for setting in read_config('tp2', 'override').split(','):
        k, v = setting.split('=', 1)
        EXTERNAL_LIBRARY_OVERRIDE[k].append(v)


def get_oss_third_party_config():
    interpreter = read_config('python#py3', 'interpreter', 'python3')
    if interpreter.endswith('python3'):
        with allow_unsafe_import():
            import subprocess
        print(
            'No explicit interpreter was provided, so python3 version '
            'detection is falling back to running the "python3" command. '
            'Update python#py3.interpreter in your .buckconfig in order to '
            'not have to run this command each time, and avoid potential '
            'problems with buck overcaching', file=sys.stderr)
        try:
            py3_version = subprocess.check_output([interpreter, '--version'])
            py3_version = py3_version.encode('utf-8').split()[1]
        except subprocess.CalledProcessError:
            print(
                '{} --version failed. python3 version could '
                'not be determined'.format(interpreter), file=sys.stderr)
            raise
    else:
        py3_version = interpreter.rpartition('python')[-1]
    py3_version = '.'.join(py3_version.split('.')[0:2])

    default_platform = read_config('cxx', 'default_platform', 'default')
    default_arch = read_config('buckit', 'architecture', 'x86_64')
    gcc_version = read_config('buckit', 'gcc_version', '4.9')
    return {
        'platforms': {
            default_platform: {
                'architecture': default_arch,
                'build': {
                    'auxiliary_versions': {},
                    'projects': {
                        'python': [('2.7', '2.7'), (py3_version, py3_version)],
                    },
                },
                'tools': {
                    'projects': {
                        'gcc': gcc_version,
                    },
                },
            },
        },
        'version_universes': [
            {
                'python': '2.7',
            },
            {
                'python': py3_version,
            },
        ],
    }


if config.third_party_config_path:
    # Load the third-party config.
    config_path = os.path.join(CELL_ROOT, config.third_party_config_path)
    add_build_file_dep('//' + config.third_party_config_path)
    with open(config_path) as f:
        code = compile(f.read(), config_path, 'exec')
    vals = {}
    eval(code, vals)
    third_party_config = vals['config']
else:
    # If we're not given a file with a third-party config (like on dev servers)
    # don't try to load the third-party-config
    third_party_config = get_oss_third_party_config()


BUILD_MODE_CACHE = {}


def get_empty_build_mode():
    return BuildMode.BuildMode('empty', BuildMode.BuildSettings())


def get_build_mode(base_path):
    """
    Look up and load the build mode settings that apply to given base path.
    """

    local_modes = BUILD_MODE_CACHE.get(base_path)
    if local_modes is not None:
        return local_modes

    local_modes = {}

    # Walk up the dir tree looking for the closest BUILD_MODE file.
    path = base_path
    while path:

        # Check for a `BUILD_MODE` file at this level of the directory tree.
        build_mode_path = os.path.join(path, 'BUILD_MODE')
        add_build_file_dep('//' + build_mode_path)
        if os.path.exists(build_mode_path):

            # Before importing, make sure to clear out existing build mode
            # settings in the `BuildMode` module.  This has two effects:
            # 1) Remove the fbconfig/fbmake defaults, since Buck uses its own
            # 2) Prevent BUILD_MODE files from leaking their changes by
            #    modifying module state.
            BuildMode.DEV = get_empty_build_mode()
            BuildMode.OPT = get_empty_build_mode()
            BuildMode.DBG = get_empty_build_mode()
            BuildMode.DBGO = get_empty_build_mode()

            # Since `include_defs` modifies the current context's globals, make
            # sure we save them and restore them before and after importing.
            current = globals()
            saved = dict(current)

            # BUILD_MODE files import the `BuildMode` module, so make sure it's
            # available via the correct name.
            sys.modules['BuildMode'] = BuildMode
            try:
                include_defs('//' + os.path.join(path, 'BUILD_MODE'))
                local_modes = current.get('modes', {})
            finally:
                del sys.modules['BuildMode']

            # Restore our globals.
            current.clear()
            current.update(saved)

            break

        path, _ = os.path.split(path)

    BUILD_MODE_CACHE[base_path] = local_modes
    return local_modes


# Add the `util` class supporting fbconfig/fbmake globs.
class Empty(object):
    pass
util = Empty()
util.files = lambda *patterns: glob(patterns)
__all__.append('util')


CXX_RULES = set([
    'cpp_benchmark',
    'cpp_binary',
    'cpp_java_extension',
    'cpp_library',
    'cpp_lua_extension',
    'cpp_python_extension',
    'cpp_unittest',
])


HEADERS_RULE_CACHE = set()


def require_default_headers_rule():
    name = '__default_headers__'
    if get_base_path() not in HEADERS_RULE_CACHE:
        HEADERS_RULE_CACHE.add(get_base_path())
        cxx_library(
            name=name,
            exported_headers=(
                glob(['**/*' + ext for ext in cxx_sources.HEADER_EXTS])
            ),
        )
    return ':' + name


def rule_handler(context, globals, rule_type, **kwargs):
    """
    Callback that fires when a TARGETS rule is evaluated, converting it into
    one or more Buck rules.
    """

    # Ignore rules flagged as fbconfig-only.
    if kwargs.get('fbconfig_only', False):
        return

    # Ingore the flag (regarless of value).
    if 'buck_only' in kwargs:
        del kwargs['buck_only']

    # Wrap the TARGETS rule into a `Rule` object.
    rule = rule_mod.Rule(type=rule_type, attributes=kwargs)

    # For full auto-headers support, add in the recursive header glob rule
    # as a dep. This is only used in fbcode for targets that don't fully
    # specify their dependencies, and it will be going away in the future
    if (config.add_auto_headers_glob and
            rule.type in CXX_RULES and
            AutoHeaders.RECURSIVE_GLOB == cpp.CppConverter.get_auto_headers(
                rule.attributes.get('headers'),
                rule.attributes.get('auto_headers'),
                read_config)):
        deps = list(rule.attributes.get('deps', []))
        deps.append(require_default_headers_rule())
        rule.attributes['deps'] = deps

    # Convert the fbconfig/fbmake rule into one or more Buck rules.
    base_path = get_base_path()
    context['buck_ops'] = (
        base.BuckOperations(
            add_build_file_dep,
            glob,
            include_defs,
            read_config))
    context['build_mode'] = get_build_mode(base_path).get(context['mode'])
    context['third_party_config'] = third_party_config
    context['config'] = config

    if rule_type == 'cpp_library_external':
        if kwargs['name'] in EXTERNAL_LIBRARY_OVERRIDE:
            # Apply settings
            for override in EXTERNAL_LIBRARY_OVERRIDE[kwargs['name']]:
                k, v = override.split('=', 1)
                simple_map = {
                    'True': True,
                    'False': False,
                }
                kwargs[k] = simple_map[v]

    results = converter.convert(base.Context(**context), base_path, [rule])
    # Instantiate the Buck rules that got converted successfully.
    for converted in results.rules:
        eval(converted.type, globals)(**converted.attributes)

    # If the rule failed to be converted, create "landmine" rules that'll
    # fire with the error message if the user tries to build them.
    for name, error in results.errors.iteritems():
        msg = 'ERROR: {}: {}'.format(name, error)
        msg = os.linesep.join(textwrap.wrap(msg, 79, subsequent_indent='  '))
        genrule(
            name=name.split(':')[1],
            out='out',
            cmd='echo {} 1>&2; false'.format(pipes.quote(msg)),
            visibility=['PUBLIC'],
        )


# Export global definitions.
for key, val in global_defns.__dict__.iteritems():
    if not key.startswith('_'):
        globals()[key] = val
        __all__.append(key)


# Helper rule to throw an error when accessing raw Buck rules.
def invalid_buck_rule(rule_type, *args, **kwargs):
    raise ValueError(
        '{rule}(): unsupported access to raw Buck rules! '
        'Please use supported fbcode rules (https://fburl.com/fbcode-targets) '
        'instead.'
        .format(rule=rule_type))


# Helper rule to ignore a Buck rule if requested by buck config.
def ignored_buck_rule(rule_type, *args, **kwargs):
    pass


def _install_converted_rules(globals, **context_kwargs):
    old_globals = globals.copy()

    # Prevent direct access to raw BUCK UI, as it doesn't go through our
    # wrappers.
    for rule_type in constants.BUCK_RULES:
        globals[rule_type] = functools.partial(invalid_buck_rule, rule_type)

    all_rule_types = constants.FBCODE_RULES + \
        ['buck_' + r for r in constants.BUCK_RULES]
    for rule_type in all_rule_types:
        globals[rule_type] = functools.partial(
            rule_handler, context_kwargs, old_globals, rule_type)

    # If fbcode.enabled_rule_types is specified, then all rule types that aren't
    # whitelisted should be redirected to a handler that's a no-op. For example,
    # only a small set of rules are supported for folks building on laptop.
    enabled_rule_types = read_config('fbcode', 'enabled_rule_types', None)
    if enabled_rule_types is not None:
        enabled_rule_types = map(unicode.strip, enabled_rule_types.split(','))
        for rule_type in set(all_rule_types) - set(enabled_rule_types):
            globals[rule_type] = functools.partial(ignored_buck_rule, rule_type)


__all__.append('install_converted_rules')
def install_converted_rules(globals, **context_kwargs):
    context_kwargs = {
        'compiler': config.compiler_family,
        'coverage': config.coverage,
        'link_style': config.default_link_style,
        'mode': config.build_mode,
        'sanitizer': config.sanitizer if config.sanitizer else None,
        'supports_lto': config.supports_lto,
    }
    _install_converted_rules(globals, **context_kwargs)
