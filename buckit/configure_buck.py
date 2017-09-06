#!/usr/bin/env python3

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import configparser
import contextlib
import fcntl
import io
import json
import logging
import os
import threading
from collections import defaultdict, namedtuple

from constants import PACKAGE_JSON, BUCKCONFIG, BUCKCONFIG_LOCAL
from helpers import BuckitException

PackageInfo = namedtuple(
    'PackageInfo',
    ['name', 'cell_name', 'cell_alias', 'absolute_path', 'includes_info']
)
IncludesInfo = namedtuple('IncludesInfo', ['path', 'whitelist_functions'])

BUCKCONFIG_HEADER = r'''
# This configuration file was updated by buckit. Manual changes
# should be made in the root project's .buckconfig /.buckconfig.local
# file. All package's .buckconfig.local files can then be updated by
# running `yarn run buckit buckconfig`

'''


__file_lock_counts = defaultdict(int)
__mutex = threading.RLock()


@contextlib.contextmanager
def __lockfile(project_root):
    """
    On enter, locks a file in the project root, on exit unlocks it. Keeps a
    count of lock attempts, so can be locked recursively
    """
    _lockfile = None
    try:
        lock_path = os.path.join(project_root, '.buckconfig.lock')
        logging.debug("Locking file at %s", lock_path)
        _lockfile = open(lock_path, 'w')
        count = 0
        with __mutex:
            __file_lock_counts[project_root] += 1
            count = __file_lock_counts[project_root]
            fcntl.lockf(_lockfile, fcntl.LOCK_EX)
            logging.debug(
                "Locked file at %s. Count is %s",
                lock_path,
                count)
        yield None
    finally:
        if _lockfile:
            with __mutex:
                __file_lock_counts[project_root] -= 1
                lock_count = __file_lock_counts[project_root]
                if lock_count == 0:
                    logging.debug("Unlocking file at %s", lock_path)
                    fcntl.lockf(_lockfile, fcntl.LOCK_UN)
                    logging.debug("Unlocked file at %s", lock_path)
                else:
                    logging.debug("Lock count is at %s, not unlocking", lock_count)
                _lockfile.close()


def update_config(project_root, buckconfig, new_properties, override=False, merge=None):
    """
    Take a dictionary of {section : {key: [values] (or a string value)}}
    and set it in a .buckconfig style file

    Arguments:
        project_root - The path to the root project. Used for locking
        buckconfig - The path to the buckconfig file
        new_properties - A dictionary of {section: key: [values]|value}. If
                         values is an iterable, it will be joined by spaces
        override - Whether or not to override existing values
        merge - If provided, a dictionary of section.key strings to delimiter
                where we should split the string by the delimiter, merge the
                values, and write them back out with the given delimiter
    """
    with __lockfile(project_root):
        __update_config(buckconfig, new_properties, override, merge)


def __update_config(buckconfig, new_properties, override=False, merge=None):
    """
    Take a dictionary of {section : {key: [values] (or a string value)}}
    and set it in a .buckconfig style file. No locking is done in this method

    Arguments:
        buckconfig - The path to the buckconfig file
        new_properties - A dictionary of {section: key: [values]|value}. If
                         values is an iterable, it will be joined by spaces
        override - Whether or not to override existing values
        merge - If provided, a dictionary of section.key strings to delimiter
                where we should split the string by the delimiter, merge the
                values, and write them back out with the given delimiter
    """
    merge = merge or {}
    config = configparser.ConfigParser()
    if os.path.exists(buckconfig):
        config.read(buckconfig)
    logging.debug("Updating file at %s", buckconfig)
    for section, kvs in new_properties.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in kvs.items():
            if override or not config.has_option(section, key):
                merge_delimiter = merge.get('{}.{}'.format(section, key))
                if isinstance(value, str):
                    str_value = value
                elif merge_delimiter:
                    if config.has_section(section):
                        existing = set(
                            (
                                x.strip()
                                for x in config.get(section, key, fallback='')
                                .split(merge_delimiter)
                            )
                        )

                    else:
                        existing = set()
                    str_value = merge_delimiter.join(existing | set(value))
                else:
                    str_value = ' '.join(value)
                logging.debug("Setting %s.%s to %s", section, key, str_value)

                config.set(section, key, str_value)
            else:
                logging.debug(
                    "%s.%s is already set, not overriding values", section, key
                )
    with open(buckconfig, 'w') as fout:
        fout.write(BUCKCONFIG_HEADER)
        config.write(fout)
    logging.debug("Updated file at %s", buckconfig)


def parse_package_info(package_path):
    """
    Try to get the package info from the package.json inside of package_path

    Arguments:
        package_path - The path to the package root that contains package.json

    Returns:
        PackageInfo object with properties from the package.json
    """

    package_path = os.path.abspath(package_path)
    json_path = os.path.join(package_path, PACKAGE_JSON)
    try:
        with open(json_path, 'r') as fin:
            js = json.loads(fin.read())
            buckit = js.get('buckit', {})
            cell_name = buckit.get('cell_name', js['name'])
            includes = buckit.get('includes', None)
            if includes:
                includes_info = IncludesInfo(
                    includes.get('path', None),
                    includes.get('whitelist_functions', [])
                )
                if not isinstance(includes_info.path, str):
                    raise BuckitException(
                        "buckit.includes in {} should be a string", json_path)
                if not isinstance(includes_info.whitelist_functions, list):
                    raise BuckitException(
                        "buckit.whitelist_functions in {} should be a list",
                        json_path)
            else:
                includes_info = None

            return PackageInfo(
                js["name"],
                cell_name.split('/')[-1],
                'yarn|{}'.format(js["name"]), package_path, includes_info
            )
    except Exception as e:
        raise BuckitException(
            "Could not read property 'buckit.name' or 'name' from "
            "json file at {}: {}", json_path, e)


def find_project_root(start_path):
    """
    Starting at start_path, going up, try to find the first directory with
    a package.json or .buckconfig, and call that the root of the project

    Args:
        start_path: The directory to start looking in
    Returns:
        The absolute path to the project root
    Raises:
        Exception: No parent project could be found
    """
    terminal = os.path.splitdrive(start_path)[0] or '/'
    path = os.path.abspath(start_path)
    while path != terminal:
        logging.debug("Checking %s for package.json or .buckconfig", path)

        package_json = os.path.join(path, PACKAGE_JSON)
        package_buckconfig = os.path.join(path, BUCKCONFIG)
        package_path = path
        path = os.path.split(path)[0]

        if os.path.exists(package_buckconfig):
            break
        elif os.path.exists(package_json):
            try:
                package_info = parse_package_info(package_path)
                logging.debug(
                    "Found project %s at %s", package_info.name, package_json
                )
                break
            except Exception:
                # If we couldn't parse it, it wasn't meant to be
                logging.debug("Could not parse json in %s", package_json)
                continue
        else:
            continue
    else:
        raise BuckitException(
            "Could not find a .buckconfig or package.json above {}. Stopped "
            "at {}", start_path, path)

    logging.debug("{bold}Found project root at %s{clear}", package_path)
    return package_path


def __update_root_buckconfig(project_root, package_info, is_root_dep):
    """
    Updates the root .buckconfig with `cell=alias` in the repositories section
    """
    buckconfig = os.path.join(project_root, BUCKCONFIG)
    repos = 'repositories'
    project = 'project'
    buildfile = 'buildfile'
    whitelist_key = 'build_file_import_whitelist'

    to_set = {
        repos: {},
        project: {},
        buildfile: {},
    }

    alias_config = '$(config repository_aliases.{})'.format(
        package_info.cell_alias
    )
    to_set[repos][package_info.cell_name] = alias_config

    if package_info.includes_info and is_root_dep:
        if package_info.includes_info.whitelist_functions:
            to_set[project][whitelist_key] = \
                package_info.includes_info.whitelist_functions

        new_includes = '//{alias_config}/{path}'.format(
            alias_config=alias_config, path=package_info.includes_info.path
        )
        to_set[buildfile]['includes'] = new_includes

    __update_config(
        buckconfig, to_set, merge={'{}.{}'.format(project, whitelist_key): ','}
    )


def __update_root_buckconfig_local(project_root, package_info):
    """
    Updates the root .buckconfig with `alias=path_relative_to_root` in the
    repository_aliases section
    """
    buckconfig_local = os.path.join(project_root, BUCKCONFIG_LOCAL)
    relative_path = os.path.relpath(package_info.absolute_path, project_root)

    logging.debug("Updating root buckconfig.local at %s", buckconfig_local)

    to_set = {'repository_aliases': {package_info.cell_alias: relative_path}}
    __update_config(buckconfig_local, to_set)


def __update_packages_buckconfig_local(project_root):
    """
    Updates all .buckconfig.local files in all directories specified in
    the root's repository_aliases section. This copies the root
    .buckconfig.local, and makes all of the paths relative to the cell
    """
    buckconfig_local = os.path.join(project_root, BUCKCONFIG_LOCAL)
    section = 'repository_aliases'

    logging.debug("Updating .buckconfig.local paths for all packages")

    config = configparser.ConfigParser()
    if not os.path.exists(buckconfig_local):
        logging.debug('.buckconfig at %s does not exist', buckconfig_local)
        return
    config.read(buckconfig_local)
    if not config.has_section(section):
        logging.debug('[%s] was not found in %s', section, buckconfig_local)
        return

    config_string = io.StringIO()
    config.write(config_string)

    for _, package_path in config.items(section):
        # For all cells, make sure they have a copy of the .buckconfig.local.
        # Update its paths to have proper relative paths, rather than the ones
        # copied from the root
        package_path = os.path.join(project_root, package_path)
        if not os.path.exists(package_path):
            logging.debug("Package path %s does not exist", package_path)
            continue

        package_buckconfig_local = os.path.join(package_path, BUCKCONFIG_LOCAL)
        package_config = configparser.ConfigParser()
        config_string.seek(0)
        package_config.read_file(config_string)

        logging.debug(
            "Updating .buckconfig.local at %s", package_buckconfig_local
        )

        for cell_alias, root_relative_path in package_config.items(section):
            relative_path = os.path.relpath(
                os.path.abspath(os.path.join(project_root, root_relative_path)),
                os.path.abspath(package_path)
            )
            package_config.set(section, cell_alias, relative_path)
        with open(package_buckconfig_local, 'w') as fout:
            fout.write(BUCKCONFIG_HEADER)
            package_config.write(fout)

        logging.debug(
            "{bold}Updated .buckconfig.local at %s{clear}",
            package_buckconfig_local
        )


def find_package_paths(
    project_root,
    node_modules,
    package_name='',
    already_found=None
):
    """
    Find all the packages in a given project root, return information about
    each of those packages.

    Arguments:
        project_root - The root path of the main project
        node_modules - The name of the node_modules directory in project_root
        package_name - The name of the package underneath node_modules, or
                       empty if the root package.json should be examined
        already_found - A list of package names that have already been
                        investigated. Used for cycle detection

    Returns a tuple of (
        dictionary of package names to paths,
        set of all of root's direct dependencies,
        dictionary of package names to original parsed json
    )
    """
    already_found = already_found or []
    jsons = {}
    if package_name:
        # Look for cells that have compiled artifacts first
        package_root = os.path.join(project_root, node_modules, package_name)
        package_json = os.path.join(package_root, PACKAGE_JSON)
    else:
        package_json = os.path.join(project_root, PACKAGE_JSON)

    # No json exists, stop looking
    if not os.path.exists(package_json):
        return {}, set(), jsons

    with open(package_json, 'r') as fin:
        js = json.loads(fin.read())

    paths = {}
    root_deps = set()

    for dep in js.get('dependencies', {}):
        if dep in already_found:
            raise BuckitException(
                'Found a cycle when finding dependencies: {}',
                ' -> '.join(already_found))
        already_found.append(dep)
        dep_paths, ignore, dep_jsons = find_package_paths(
            project_root, node_modules, dep, already_found
        )
        paths.update(dep_paths)
        jsons.update(dep_jsons)
        if not package_name:
            root_deps.add(dep)
        del already_found[-1]

    if package_name:
        paths[package_name] = package_root
        jsons[package_name] = js
    return paths, root_deps, jsons


def configure_buck_for_all_packages(project_root, node_modules):
    """
    Configures buck for all packages that can be found in the project. This
    includes all transitive dependencies as well

    File locking is done to avoid this method being run by multiple processes
    at once

    Arguments:
        project_root - The root path of the main project
        node_modules - The name of the node_modules directory in project_root
    """
    with __lockfile(project_root):
        package_paths, root_deps, jsons = find_package_paths(
            project_root, node_modules
        )

        for package_name, package_path in package_paths.items():
            configure_buck_for_package(
                project_root, package_name, package_path, root_deps, False
            )
        __update_packages_buckconfig_local(project_root)

    return 0


def configure_buck_for_package(
    project_root,
    package_name,
    package_path,
    root_deps,
    update_all_package_buckconfigs=True
):
    """
    Configure .buckconfig and .buckconfig.local in a project to use a given
    package

    File locking is done to avoid this method being run by multiple processes
    at once

    Arguments:
        project_root - The root of the project where .buckconfig lives
        package_name - The name of the package to configure in the root project
                       (e.g. @buckpkg/folly)
        package_path - The path to the package's root
        root_deps - The list of packages that are in the root project's
                    dependencies list
        update_all_package_buckconfigs - Whether or not to update all of the
                                         .buckconfig.local files in all cells
                                         in the project
    """
    with __lockfile(project_root):
        package_path = package_path.rstrip('/')
        package_info = parse_package_info(package_path)
        __update_root_buckconfig(
            project_root, package_info, package_name in root_deps
        )
        __update_root_buckconfig_local(project_root, package_info)
        if update_all_package_buckconfigs:
            __update_packages_buckconfig_local(project_root)
    return 0
