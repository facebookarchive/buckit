#!/usr/bin/env python3

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import logging
import os
import platform
import subprocess

from constants import BUCKCONFIG_LOCAL
from configure_buck import update_config, find_package_paths
from formatting import readable_check_call


def get_for_current_system(options, default=None):
    """
    Takes an object of one of the following forms, and tries to find an option
    that makes sense for the current platform. Returns `default` if nothing was
    found

    Arguments:
        options - Dictionary of: {<platform>: {<version>: <data>}}. Platform
                  can be either linux, darwin, windows or default. Default will
                  be used if present. For versions, they should be a dotted
                  version string. An attempt will be made to match as many of
                  the pieces of the version as possible. If no version matches,
                  the 'default' key will be attempted. On linux, this version
                  is the version from platform/distro.linux_distribution.
                  If no version can be found that matches, "default" will be
                  returned
        default - The default value to return if no match is found
    """
    if not isinstance(options, dict):
        return options

    system = platform.system()
    version = None
    if system == 'Linux':
        # This is going to be removed in 3.7, but it's a bit of a pain to get
        # distro() installed
        try:
            import distro
            linux_distribution = distro.linux_distribution
        except ImportError:
            if not hasattr(platform, 'linux_distribution'):
                logging.error(
                    "{red}The distro python module is not installed, and "
                    "platform.linux_distribution() does not exist. Please "
                    "install distro with `pip install distro`{clear}"
                )
                raise
            linux_distribution = platform.linux_distribution
        system, version_str, id = linux_distribution(
            full_distribution_name=False
        )
    elif system == 'Windows':
        version_str = platform.win32_ver()[1]
    elif system == 'Darwin':
        version_str = platform.mac_ver()[0]

    system = system.lower()
    system_selection = options.get(system, None)
    if system_selection is None:
        return options.get('default', default)

    if not isinstance(system_selection, dict):
        return system_selection

    # Take a very non-strict version check. We will check as many components
    # of the version as are common in both versions. e.g. if '7' is in the
    # map, and our version is '7.1.3', then we've found a match. We make sure
    # to sort the keys in descending order, first, to make sure that we
    # handle sub versions properly
    version = version_str.split('.')
    keys = sorted(system_selection.keys(), reverse=True)
    for key in keys:
        found_version = key.split('.')
        if all((x == y for x, y in zip(found_version, version))):
            return system_selection[key]
    return system_selection.get('default', default)


def install_system_packages(packages):
    if not packages:
        return

    logging.info("Installing system packages: %s", packages)
    commands = {
        # TODO: Seems that brew can sometimes return 1 when all packages are
        #       installed
        'darwin': [['brew', 'install'], ['brew', 'upgrade']],
        'centos': [['sudo', 'yum', 'install', '-y']],
        'ubuntu': [['sudo', 'apt', 'install', '-y']],
    }
    cmds = get_for_current_system(commands, None)
    if not cmds:
        logging.warning(
            '{yellow}Could not get an installer command for this system, not '
            'installing %s{clear}', packages
        )
        return
    errors = []
    for cmd in cmds:
        cmd = cmd + list(packages)
        try:
            readable_check_call(cmd, action='installing system packages')
            break
        except subprocess.CalledProcessError as e:
            error = '{} failed with code {}'.format(
                '\n'.join(cmd), e.returncode)
            errors += error
            logging.debug(error)
    else:
        logging.warning(
            '{yellow}No install commands succeeded. Errors were:%s{clear}',
            '\n'.join([' - ' + error for error in errors]))


def get_system_packages(project_root, node_modules, only_required):
    paths, root_pkgs, jsons = find_package_paths(project_root, node_modules)
    system_packages = set()
    for js in jsons.values():
        all_pkgs = js.get('buckit', {}).get('required_system_packages', {})
        pkgs = get_for_current_system(all_pkgs, [])
        if not only_required:
            all_pkgs.update(js.get('buckit', {}).get('system_packages', {}))
            pkgs += get_for_current_system(all_pkgs, [])
        system_packages |= set(pkgs)
    return system_packages


def use_system_packages(
    project_root, node_modules, install_packages,
    use_system_for_all
):
    if install_packages:
        # Get packages
        system_packages = get_system_packages(
            project_root,
            node_modules,
            only_required=not use_system_for_all
        )
        # Install them
        install_system_packages(system_packages)
    # Make sure that they're used
    if use_system_for_all:
        to_set = {'buckit': {}}
        if use_system_for_all:
            to_set['buckit']['use_system_for_all'] = 'true'
        else:
            to_set['buckit']['use_system_for_all'] = 'false'
        buckconfig_local = os.path.join(project_root, BUCKCONFIG_LOCAL)
        update_config(project_root, buckconfig_local, to_set, override=True)
    return 0
