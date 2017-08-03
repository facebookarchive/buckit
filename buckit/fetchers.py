#!/usr/bin/env python3

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import glob
import hashlib
import logging
import os
import platform
import shlex
import shutil
import subprocess
import tempfile

from collections import namedtuple

from configure_buck import find_project_root, update_config
from constants import BUCKFILE, BUCKCONFIG
from formatting import readable_check_call
from textwrap import indent, dedent

PipPythonSettings = namedtuple(
    'PipPythonSettings', [
        'virtualenv_command',
        'virtualenv_root',
        'pip_package',
        'pip_version',
        'prefix_subdir',
    ]
)


class CachedFetcher:

    def should_fetch(self, destination, force):
        src_dest = os.path.join(destination, 'src')
        return not os.path.exists(src_dest) or force

    def populate_cache(self, destination, use_proxy):
        raise Exception('Not implemented')

    def fetch(self, project_root, destination, use_proxy):
        destination = os.path.join(destination, 'src')
        if os.path.isdir(destination):
            return

        # Make sure that our parent dir exists
        if not os.path.exists(os.path.split(destination)[0]):
            os.makedirs(os.path.split(destination)[0], 0o0755)

        yarn_cache = os.path.join(os.path.expanduser('~'), '.cache', 'yarn')
        if not os.path.exists(yarn_cache):
            yarn_cache = os.path.join(os.path.expanduser('~'), '.yarn-cache')
        if not os.path.exists(yarn_cache):
            os.makedirs(yarn_cache)

        clean_package_name = self.package_name.replace('/',
                                                       '_').replace('\\', '_')
        clean_version = self.version().replace('/', '_').replace('\\', '_')
        cache_dir_name = 'buckit-fetch-{}-{}'.format(
            clean_package_name, clean_version
        )
        cache_dir = os.path.join(yarn_cache, cache_dir_name)
        if not os.path.exists(cache_dir):
            logging.debug(
                "{bold}Downloading %s to cache directory at %s{clear}",
                self.package_name, cache_dir
            )
            self.populate_cache(cache_dir, use_proxy)

        tmp_destination = tempfile.mkdtemp(dir=os.path.split(destination)[0])
        logging.debug(
            "{bold}Cached download at %s exists, copying to %s{clear}",
            cache_dir, tmp_destination
        )
        # Dir needs to not exist for copytree, but we want mkdtemp for guaranteed
        # unique temp dir next to destination
        tmp_subdir = os.path.join(
            tmp_destination, os.path.split(destination)[1]
        )
        try:
            shutil.copytree(cache_dir, tmp_subdir, symlinks=True)
            shutil.move(tmp_subdir, destination)
        finally:
            if os.path.exists(tmp_destination):
                shutil.rmtree(tmp_destination)


class GitFetcher(CachedFetcher):

    def __init__(self, package_name, json_file, url, commit, tag):
        if bool(commit) == bool(tag):
            raise Exception(
                "{}: Either the commit, or the tag must be specified".
                format(json_file)
            )

        self.package_name = package_name
        self.url = url
        self.commit = commit
        self.tag = tag

    def version(self):
        return self.commit or self.tag

    def populate_cache(self, destination, use_proxy):
        env = dict(os.environ)
        if not use_proxy:
            for var in ('https_proxy', 'http_proxy'):
                if var in env:
                    del env[var]

        tmp_dir = tempfile.mkdtemp(dir=os.path.split(destination)[0])
        out_dir = os.path.join(tmp_dir, 'outdir')
        try:
            if self.commit:
                # Github and the like don't seem to let you do git fetch <sha>
                # so we have to do a heavy weight clone
                readable_check_call(
                    ['git', 'clone', '--recursive', self.url, out_dir],
                    'cloning repo'
                )
                readable_check_call(
                    ['git', 'checkout', self.commit],
                    'checking out specific commit',
                    cwd=out_dir
                )
            else:
                if platform.system() == 'Darwin':
                    # For now short circuit shallow submodules on osx
                    # because things are terrible there.
                    shallow_submodules = []
                else:
                    shallow_submodules = ['--shallow-submodules']

                readable_check_call(
                    [
                        'git',
                        'clone',
                        '--branch',
                        self.tag,
                        '--depth',
                        '1',
                        '--recursive',
                    ] + shallow_submodules + [self.url, out_dir], 'cloning repo'
                )
            logging.info(
                "Checked out %s to %s, moving it to %s", self.url, out_dir,
                destination
            )
            shutil.move(out_dir, destination)
        finally:
            shutil.rmtree(tmp_dir)


class HttpTarballFetcher(CachedFetcher):
    HASH_BUFFER_SIZE = 64 * 1024

    def __init__(self, package_name, json_file, url, sha256):
        self.package_name = package_name
        self.url = url
        self.sha256 = sha256

    def version(self):
        return self.sha256

    def populate_cache(self, destination, use_proxy):
        env = dict(os.environ)
        if not use_proxy:
            for var in ('https_proxy', 'http_proxy'):
                if var in env:
                    del env[var]
        tmp_dir = tempfile.mkdtemp(dir=os.path.split(destination)[0])
        tmp_file = os.path.join(tmp_dir, 'output_file')
        try:
            readable_check_call(
                ['curl', self.url, '-L', '-o', tmp_file],
                'fetching {}'.format(self.url)
            )
            self.check_hash(tmp_file)
            readable_check_call(
                ['tar', 'xf', tmp_file, '-C', tmp_dir],
                'extracting {}'.format(tmp_file)
            )
            os.remove(tmp_file)
            main_dir = glob.glob(os.path.join(tmp_dir, '*'))[0]
            logging.info("{bold}Moving %s to %s", main_dir, destination)
            shutil.move(main_dir, destination)
        finally:
            shutil.rmtree(tmp_dir)

    def check_hash(self, filename):
        file_hash = hashlib.sha256()
        with open(filename, 'rb') as fin:
            while True:
                data = fin.read(self.HASH_BUFFER_SIZE)
                if not data:
                    break
                file_hash.update(data)

        if file_hash.hexdigest() != self.sha256:
            raise Exception(
                'SHA256 of downloaded file didn\'t match! Expected '
                '{}, got {}'.format(self.sha256, file_hash.hexdigest())
            )


class PipFetcher:

    def __init__(
        self, package_name, json_file, pip2_package, pip2_version, pip3_package,
        pip3_version, main_rule, buck_deps, python_settings
    ):
        self.package_name = package_name
        self.main_rule = main_rule
        self.buck_deps = buck_deps
        self.python2 = None
        self.python3 = None
        if pip2_package and python_settings.use_python2:
            self.python2 = PipPythonSettings(
                python_settings.python2_virtualenv_command,
                python_settings.python2_virtualenv_root,
                pip2_package,
                pip2_version,
                'py2',
            )
        if pip3_package and python_settings.use_python3:
            self.python3 = PipPythonSettings(
                python_settings.python3_virtualenv_command,
                python_settings.python3_virtualenv_root,
                pip3_package,
                pip3_version,
                'py3',
            )
        self.python2_files = {"srcs": {}, "bins": {}}
        self.python3_files = {"srcs": {}, "bins": {}}

        if not main_rule:
            raise Exception(
                'A main_rule attribute must be set in {}'.format(json_file)
            )

    def should_fetch(self, destination, force):
        buckfile = os.path.join(destination, BUCKFILE)
        return not os.path.exists(buckfile) or force

    def fetch(self, project_root, destination, use_proxy):
        env = dict(os.environ)
        if not use_proxy:
            for var in ('https_proxy', 'http_proxy'):
                if var in env:
                    del env[var]

        if not os.path.exists(destination):
            os.makedirs(destination)

        if self.python2:
            self.python2_files = self.install_and_get_files(
                self.python2,
                'pip',
                env,
            )
            self.setup_install_prefix(self.python2, destination)
        if self.python3:
            self.python3_files = self.install_and_get_files(
                self.python3, 'pip', env
            )
            self.setup_install_prefix(self.python3, destination)

        buckfile = os.path.join(destination, BUCKFILE)
        with open(buckfile, 'w') as fout:
            fout.write('\n'.join(self.buckfile()))
        if self.python2 or self.python3:
            read_only_props = {'project': {'read_only_paths': []}}
            project_root = find_project_root(destination)
            relative_path = os.path.relpath(destination, project_root)
            if self.python2:
                read_only_props['project']['read_only_paths'].append(
                    os.path.join(relative_path, 'py2')
                )
            if self.python3:
                read_only_props['project']['read_only_paths'].append(
                    os.path.join(relative_path, 'py3')
                )
            read_only_props['project']['read_only_paths'] = ','.join(
                read_only_props['project']['read_only_paths']
            )

            buckconfig = os.path.join(project_root, BUCKCONFIG)
            update_config(project_root, buckconfig, read_only_props)

    def buckfile(self):
        ret = []

        py2_srcs = ""
        py3_srcs = ""

        if self.python2:
            py2_srcs = '\n'.join(
                [
                    'r"{}": r"{}",'.format(
                        module_path,
                        os.path.join(self.python2.prefix_subdir, venv_relative)
                    )
                    for venv_relative, module_path in self.python2_files["srcs"]
                    .items()
                ]
            )
        if self.python3:
            py3_srcs = '\n'.join(
                [
                    'r"{}": r"{}",'.format(
                        module_path,
                        os.path.join(self.python3.prefix_subdir, venv_relative)
                    )
                    for venv_relative, module_path in self.python3_files["srcs"]
                    .items()
                ]
            )
        deps = '\n'.join(['"{}",'.format(dep) for dep in self.buck_deps])

        ret.append(
            dedent(
                """
            __py2_srcs = {{
            {py2_srcs}
            }}
            __py3_srcs = {{
            {py3_srcs}
            }}
            __preferred_srcs = __py3_srcs
            if read_config('buckit', 'python_version', '') == '2':
                __preferred_srcs = __py2_srcs
            python_library(
                name="{name}",
                srcs=__preferred_srcs,
                platform_srcs=[
                    ('py2.*', __py2_srcs),
                    ('py3.*', __py3_srcs),
                ],
                deps=[
            {deps}
                ],
                visibility=['PUBLIC'],
            )

            """
            ).format(
                name=self.main_rule,
                py2_srcs=indent(py2_srcs, ' ' * 4),
                py3_srcs=indent(py3_srcs, ' ' * 4),
                deps=indent(deps, ' ' * 8)
            )
        )

        for name, path in self.python3_files["bins"].items():
            ret.append(
                dedent(
                    """
                if read_config('buckit', 'python_version', '3') == '3':
                    sh_binary(
                        name="{name}",
                        main=r"{path}",
                    )
                """
                ).format(name=name, path=path)
            )

        for name, path in self.python2_files["bins"].items():
            ret.append(
                dedent(
                    """
                if read_config('buckit', 'python_version', '3') == '2':
                    sh_binary(
                        name="{name}",
                        main=r"{path}",
                    )
                """
                ).format(name=name, path=path)
            )
        return ret

    def parse_pip_output(self, python_settings, output):
        found_bins = []
        found_files = []
        found_files_line = False
        location = ''
        for line in output.splitlines():
            if line == 'Files:':
                found_files_line = True
            elif line.startswith('Location:'):
                location = line.split(':', 2)[1].strip()
            elif found_files_line:
                if not line.startswith('  '):
                    found_files_line = False
                    continue

                normalized = os.path.normpath(line.strip())
                if normalized.endswith('.py'):
                    found_files.append(normalized)
                elif 'bin' in normalized.split(os.sep):
                    found_bins.append(normalized)

        return self.transform_pip_output(
            python_settings, location, found_files, found_bins
        )

    def transform_pip_output(
        self, python_settings, location, found_files, found_bins
    ):
        bins = {}
        files = {}
        # Get the path relative to the root of the venv so that we can put that
        # in the buck file, and remap it to the path within system-packages
        # so that you can import the module properly
        for path in found_files:
            full_path = os.path.normpath(os.path.join(location, path))
            if full_path.startswith(python_settings.virtualenv_root + os.sep):
                venv_relative_path = full_path[
                    len(python_settings.virtualenv_root) + len(os.sep):
                ]
            else:
                venv_relative_path = path
            files[venv_relative_path] = path

        for path in found_bins:
            full_path = os.path.normpath(os.path.join(location, path))
            if full_path.startswith(python_settings.virtualenv_root + os.sep):
                venv_relative_path = full_path[
                    len(python_settings.virtualenv_root) + len(os.sep):
                ]
            else:
                venv_relative_path = path
            bins[os.path.split(path)[1]] = venv_relative_path
        return {"srcs": files, "bins": bins}

    def install_and_get_files(self, python_settings, pip_command, env):
        # TODO: Windows
        activate_path = os.path.join(
            python_settings.virtualenv_root, 'bin', 'activate'
        )
        if (not os.path.exists(python_settings.virtualenv_root) or
                not os.path.exists(activate_path)):
            logging.info(
                "Virtualenv at %s does not exist, creating",
                python_settings.virtualenv_root
            )
            readable_check_call(
                python_settings.virtualenv_command +
                [python_settings.virtualenv_root],
                "installing python virtual env",
                env=env,
            )

        package = shlex.quote(
            python_settings.pip_package + (python_settings.pip_version or '')
        )
        command = (
            "source bin/activate && {pip} install -I {package} && "
            "{pip} show -f {package}"
        ).format(
            pip=pip_command, package=package
        )
        logging.info(
            "Installing %s via pip with %s in %s", package, command,
            python_settings.virtualenv_root
        )
        proc = subprocess.Popen(
            args=command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            cwd=python_settings.virtualenv_root,
            shell=True,
            env=env,
        )
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            logging.error(
                "{red}Error installing into virtualenv:{clear}\n"
                "stdout: %sstderr: %s\nReturn code %s\n", stdout, stderr,
                proc.returncode
            )
            raise Exception(
                "Could not install virtualenv at {}".
                format(python_settings.virtualenv_root)
            )

        stdout = stdout.decode('utf-8')

        return self.parse_pip_output(python_settings, stdout)

    def setup_install_prefix(self, python_settings, destination):
        platform_install_prefix = os.path.join(
            destination, python_settings.prefix_subdir
        )
        if not os.path.exists(destination):
            os.makedirs(destination)
        if not os.path.exists(platform_install_prefix):
            # TODO: Windows
            relative_install_prefix = os.path.relpath(
                os.path.realpath(
                    python_settings.virtualenv_root,
                ),
                os.path.realpath(os.path.split(platform_install_prefix)[0]),
            )
            logging.debug(
                "%s does not exist. Linking it to %s via %s",
                platform_install_prefix, python_settings.virtualenv_root,
                relative_install_prefix
            )

            os.symlink(
                relative_install_prefix,
                platform_install_prefix,
            )
