#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import os
import sys
import copy
import collections
import errno
import pipes
from contextlib import contextmanager

# The high-level build mode object, which gives build flags a name
# and help message.
BuildMode = collections.namedtuple('BuildMode', ['help', 'settings'])

# The flags we can override.  These are exposed as makefile variables
# named BUILD_MODE_*.  Make sure these are consistent with the per-
# language rule generator code.
def BuildSettings(**kwargs):
    # A hack to support default arguments in namedtuples
    for field in _BuildSettings._fields:
        if field not in kwargs:
            kwargs[field] = []
    return _BuildSettings(**kwargs)
_BuildSettings = collections.namedtuple('BuildSettings', [
    # C/C++ family
    'ASPPFLAGS',
    'CPPFLAGS',
    'CXXPPFLAGS',
    'CFLAGS',
    'CXXFLAGS',
    'LDFLAGS',
    #Compiler specific C/C++ flags
    #A flag should not be added here if it could be added to another flag group
    'CLANGFLAGS',
    'GCCFLAGS',

    # Go
    'GOBUILDFLAGS',

    # Java
    'JAVAFLAGS',

    # D
    'DMDFLAGS',
    'GDCFLAGS',
    'LDCFLAGS',

    # Python PARs
    'PARFLAGS',

    # Haskel
    'GHCFLAGS',
])


def combine(modes, help=None, extra_settings=None):
    """
    Return a new build mode that is formed by concatenating flags from
    the given build modes.
    """

    names = modes.keys()
    names.sort()
    name = '-'.join(names)

    if help is None:
        help = 'combination of %s' % ', '.join(names)

    settings = BuildSettings(**extra_settings or {})
    for mode in modes.itervalues():
        for field in _BuildSettings._fields:
            getattr(settings, field).extend(getattr(mode.settings, field))

    return name, BuildMode(help=help, settings=settings)


def copy_mode(mode):
    """
    Return a copy the given build mode.  Use a deep copy so that flags
    can be appended to the new build mode.
    """

    return copy.deepcopy(mode)


def make_flag(flag):
    """
    Creates a build mode that adds a single preprocessor symbol.
    Useful with combine().
    """
    return BuildMode(help='flag: ' + flag, settings=BuildSettings(
            ASPPFLAGS=['-D' + flag],
            CPPFLAGS=['-D' + flag],
            CXXPPFLAGS=['-D' + flag],
           ))


def get_build_mode_var(domain, name):
    parts = []
    parts.append('BUILD_MODE')
    if domain:
        parts.append(domain)
    parts.append(name)
    return '_'.join(parts)


def get_makefile_vars(modes):
    """
    Return the appropriate command arguments ready to pass into 'make'
    to use this build mode.
    """

    mvars = {}

    for domain, mode in modes.iteritems():
        for key in _BuildSettings._fields:
            var = get_build_mode_var(domain, key)
            val = getattr(mode.settings, key) or []
            mvars[var] = ' '.join([pipes.quote(v) for v in val])

    return mvars


def get_makefile_args(mode):
    """
    Return the appropriate command arguments ready to pass into 'make'
    to use this build mode.
    """

    args = []

    for name, val in get_makefile_vars(mode):
        args.append('%s=%s' % (name, val))

    return args


def walkdirs(path):
    dirs = []
    for part in os.path.normpath(path).split(os.sep):
        dirs.append(part)
        yield os.path.join(*dirs)


# Debug build mode. This adds debug symbols and does not perform optimization,
# to get the best possible support for debugging.
dbg_cflags = ['-g']
dbg_cppflags = ['-g']
dbg_asppflags = dbg_cppflags
DBG = BuildMode(help='debug build', settings=BuildSettings(
    ASPPFLAGS=dbg_asppflags,
    CPPFLAGS=dbg_cppflags,
    CXXPPFLAGS=dbg_cppflags,
    CFLAGS=dbg_cflags,
    CXXFLAGS=dbg_cflags,
    JAVAFLAGS=['-g'],
    GDCFLAGS=['-g', '-fdebug', '-fassert', '-Wall', '-Werror'],
    DMDFLAGS=['-g', '-debug', '-w'],
    LDCFLAGS=['-g', '-d-debug', '-w'],
    # See discussion of UUID in dev build mode.
    LDFLAGS=['-Wl,--build-id=uuid'],
    GOBUILDFLAGS=['-race', '-tags', 'debug'],
    GHCFLAGS=['-O0'],
))

# Dev build mode is a build mode optimized for compilation speed.
# The code it produces should behave identically to that produced
# by opt builds, except that it may have different performance
# characteristics. This lets you quickly build your code and run
# tests.
DEV = BuildMode(help='dev build', settings=BuildSettings(
    # We use the same compiler flags as for dbg mode, so that dbg and dev
    # generate hits for each other in ccache.
    JAVAFLAGS=DBG.settings.JAVAFLAGS,
    GDCFLAGS=DBG.settings.GDCFLAGS,
    DMDFLAGS=DBG.settings.DMDFLAGS,
    LDCFLAGS=DBG.settings.LDCFLAGS,
    GOBUILDFLAGS=DBG.settings.GOBUILDFLAGS,

    # In dev builds, we only use the 'uuid' option for the build-id.
    # (This generates a build-id as a random number instead of using a
    # sha1 of the binary.)
    #
    # The reason for this is that computing the sha1 accounts for
    # about 15% of the total link time.  This is several seconds on
    # larger projects.
    #
    # The build-id is used for the perf tool, and for optimized builds
    # the time it takes to link isn't so bad.  At the time of this
    # writing we don't know of a strong reason to prefer sha1 to a
    # random id even in an optimized build, but since optimized build
    # link time is not as important we're still using the sha1 in that
    # case, in case we run into DWARF-based tools that want to
    # recompute the sha1 and see if they match or something like that.
    #
    # See discussion on D666587.
    #
    # We also strip the debug symbols to save linking time.
    LDFLAGS=['-Wl,-S', '-Wl,--build-id=uuid'],
))

# Debug optimized build. This is a binary with assertions and other debug
# checks on, but compiled at a higher optimization level than -O0. It will be
# roughly useless for debugging but makes test runs significantly faster while
# preserving assertions. Compilation does take slightly longer but for long
# test runs it trivially makes up for it.
dbgo_cflags = ['-g', '-O2', '-fno-omit-frame-pointer']
dbgo_cppflags = ['-g']
dbgo_asppflags = dbgo_cppflags
DBGO = BuildMode(help='debug optimized build', settings=BuildSettings(
    ASPPFLAGS=dbgo_asppflags,
    CPPFLAGS=dbgo_cppflags,
    CXXPPFLAGS=dbgo_cppflags,
    CFLAGS=dbgo_cflags,
    CXXFLAGS=dbgo_cflags,
    JAVAFLAGS=['-g'],
    GDCFLAGS=['-g', '-fdebug', '-fassert', '-Wall', '-Werror'],
    DMDFLAGS=['-g', '-debug', '-w'],
    LDCFLAGS=['-g', '-d-debug', '-w'],
    # See discussion of UUID in dev build mode.
    LDFLAGS=['-Wl,--build-id=uuid'],
    GOBUILDFLAGS=DBG.settings.GOBUILDFLAGS,
))


opt_cflags = [
    '-g', '-O3', '-fno-omit-frame-pointer', '-momit-leaf-frame-pointer']
opt_cppflags = ['-g', '-DNDEBUG', '-DFBCODE_OPT_BUILD']
opt_asppflags = opt_cppflags
OPT = BuildMode(help='optimized build', settings=BuildSettings(
    ASPPFLAGS=opt_asppflags,
    CPPFLAGS=opt_cppflags,
    CXXPPFLAGS=opt_cppflags,
    CFLAGS=opt_cflags,
    CXXFLAGS=opt_cflags,
    CLANGFLAGS=[],
    GCCFLAGS=[],
    DMDFLAGS=['-g', '-w', '-O', '-inline', '-release'],
    GDCFLAGS=['-g', '-Wall', '-Werror', '-O3', '-frelease'],
    LDCFLAGS=['-g', '-w', '-O3', '-release'],
    PARFLAGS=['--optimize'],
    # See above about --build-id.
    LDFLAGS=['-O3', '-Wl,--build-id'],
    GHCFLAGS=['-O'],
))

class BuildModeLoader(object):
    """
    A class that loads in and caches build mode configuration files.
    """

    build_mode_basename = 'BUILD_MODE'
    default_modes = {
        'dbg': DBG,
        'dbgo': DBGO,
        'dev': DEV,
        'opt': OPT,
    }

    def __init__(self):
        self._cache = {}

    def _find_mode_file(self, path):
        for dir in reversed(list(walkdirs(path))):
            build_mode_file = os.path.join(dir, self.build_mode_basename)
            if os.path.exists(build_mode_file):
                return build_mode_file
        return None

    def _get_mode_name_from_path(self, path):
        return path.replace('/', '_').replace('-', '_').upper()

    def _load_mode_file(self, path):
        """
        Load the build mode file from the given path.
        """

        # Mock 'allow_unsafe_import()' context manager
        @contextmanager
        def allow_unsafe_import():
            yield

        vars = {
            'BuildMode': sys.modules[__name__],
            'allow_unsafe_import': allow_unsafe_import,
        }

        execfile(path, vars)

        build_modes = vars.get('modes', self.default_modes)

        default_name = self._get_mode_name_from_path(os.path.dirname(path))
        build_mode_name = vars.get('name', default_name)

        return build_mode_name, build_modes

    def _load(self, path):
        filename = self._find_mode_file(path)
        if filename is None:
            name = ''
            modes = self.default_modes
        else:
            name, modes = self._load_mode_file(filename)
        return name, filename, modes

    def load(self, path):
        path = os.path.normpath(path)
        ret = self._cache.get(path)
        if ret is None:
            ret = self._load(path)
            self._cache[path] = ret
        return ret

    def load_all(self, paths):
        modes = {}
        modes[''] = self.default_modes
        for path in paths:
            try:
                name, extra_modes = self._load_mode_file(path)
                # Make sure default modes are always available.
                pmodes = dict(self.default_modes)
                pmodes.update(extra_modes)
                modes[name] = pmodes
            except IOError as e:
                # Unable to read the BUILD_MODE file. This is probably because
                # the file was deleted, in which case fbconfig and fbmake will
                # be rerun. If that is the case, just continue.
                if e.errno != errno.ENOENT:
                    raise
        return modes
