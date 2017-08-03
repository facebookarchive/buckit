#!/usr/bin/env python3

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import logging
import os
import subprocess
import platform

from constants import BUCKCONFIG_LOCAL
from configure_buck import update_config


def get_current_platform_flavor():
    platforms = {
        'Darwin': 'macos',
        'Linux': 'linux',
        'Windows': 'windows',
    }
    return platforms.get(platform.system(), 'default')


def is_exe(fpath):
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def which(program, get_canonical=False):
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return os.path.realpath(program) if get_canonical else program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return os.path.realpath(exe_file) if get_canonical else exe_file

    return None


def detect_py2():
    return which('python2')


def detect_py3():
    return which('python3', get_canonical=True)


def detect_python_libs(python):
    # We want to strip version and site-packages off from the path to get lib
    # path
    return subprocess.check_output([
        python,
        '-c',
        (
            'from __future__ import print_function; '
            'from distutils import sysconfig; '
            'import os; '
            'print(os.sep.join(sysconfig.get_python_lib().split(os.sep)[:-2]))'
        )]).decode('utf-8').split('\n')[0]


def detect_python_include(python):
    return subprocess.check_output([
        python,
        '-c',
        (
            'from __future__ import print_function; '
            'from distutils import sysconfig; '
            'print(sysconfig.get_python_inc())'
        )]).decode('utf-8').split('\n')[0]


def get_system_lib_paths():
    libs = {
        'linux': [
            '/usr/local/lib64',
            '/usr/local/lib',
            '/usr/lib64',
            '/usr/lib',
            '/lib64',
            '/lib',
        ],
        'macos': [
            '/usr/local/lib',
            '/usr/local/opt/{name}/lib',
            '/usr/lib',
        ],
    }
    return libs[get_current_platform_flavor()]


def detect_cc():
    if 'CC' in os.environ:
        return os.environ['CC']

    clang = which('clang')
    if clang:
        return clang

    gcc = which('gcc')
    if gcc:
        return gcc


def detect_cxx():
    if 'CXX' in os.environ:
        return os.environ['CXX']

    clang_pp = which('clang++')
    if clang_pp:
        return clang_pp

    g_pp = which('g++')
    if g_pp:
        return g_pp

    return None


def detect_c_standard(compiler_cmd):
    versions = [
        '-std=gnu11',
        '-std=c11',
        '-std=gnu99',
        '-std=c99',
    ]
    for version in versions:
        logging.debug("Checking %s support for -std=%s", compiler_cmd, version)
        cmd = [compiler_cmd, version, '-x', 'c', '-']
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        stdout, stderr = proc.communicate(
            'int main() { return 0; }'.encode('utf-8')
        )
        if proc.returncode != 0:
            logging.debug(
                "Got return code %s, output: %s. trying next", proc.returncode,
                stdout
            )
        else:
            return version

    return None


def detect_cxx_standard(compiler_cmd):
    versions = [
        # '-std=gnu++1z',
        # '-std=c++1z',
        '-std=gnu++14',
        '-std=c++14',
        '-std=gnu++1y',
        '-std=c++1y',
        '-std=gnu++11',
        '-std=c++11',
    ]
    for version in versions:
        logging.debug("Checking %s support for -std=%s", compiler_cmd, version)
        cmd = [compiler_cmd, version, '-x', 'c++', '-']
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        stdout, stderr = proc.communicate(
            'int main() { return 0; }'.encode('utf-8')
        )
        if proc.returncode != 0:
            logging.debug(
                "Got return code %s, output: %s. trying next", proc.returncode,
                stdout
            )
        else:
            return version

    return None


def configure_compiler(project_root):
    """
    Sets up .buckconfig.local in the root project with
    basic c++/c compiler settings. More advanced probing
    will probably be done in the future
    """
    buckconfig_local = os.path.join(project_root, BUCKCONFIG_LOCAL)

    logging.info("{bold}Detecting compiler{clear}")
    current_platform = get_current_platform_flavor()
    cc = detect_cc()
    cxx = detect_cxx()
    if not cc or not cxx:
        logging.warn("Could not find clang or g++ in PATH")
        return 0

    c_standard = detect_c_standard(cc)
    if c_standard:
        cflags = [c_standard]
    else:
        cflags = []

    cxx_standard = detect_cxx_standard(cxx)
    if cxx_standard:
        cxxflags = [cxx_standard]
    else:
        cxxflags = []

    py2 = detect_py2()
    py3 = detect_py3()
    py2_include = detect_python_include(py2)
    py2_libs = detect_python_libs(py2)
    py3_include = detect_python_include(py3)
    py3_libs = detect_python_libs(py3)

    to_set = {
        'cxx': {
            'cflags': cflags + ['-pthread', '-g'],
            'cxxflags': cxxflags + ['-pthread', '-g'],
            'ldflags': ['-pthread'],
            'cxx': [cxx],
            'cc': [cc],
        },
    }
    to_set['cxx#' + current_platform] = to_set['cxx'].copy()
    to_set['cxx']['default_platform'] = current_platform

    py2_settings = {
        'interpreter': py2,
        'includes': py2_include,
        'libs': py2_libs,
    }

    py3_settings = {
        'interpreter': py3,
        'includes': py3_include,
        'libs': py3_libs,
    }

    if py2:
        to_set['python#py2'] = py2_settings
        to_set['python#py2-%s' % current_platform] = py2_settings

    if py3:
        to_set['python#py3'] = py3_settings
        to_set['python#py3-%s' % current_platform] = py3_settings

    to_set['buckit'] = {'system_lib_paths': ','.join(get_system_lib_paths())}

    update_config(project_root, buckconfig_local, to_set)
    return 0
