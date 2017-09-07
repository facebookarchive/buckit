#!/usr/bin/env python3

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import argparse
import copy
import logging
import os
import sys

from textwrap import dedent

import compiler
import configure_buck
import fetch
import formatting
import use_system
from helpers import BuckitException

log_levels = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class EnvDefault(argparse.Action):

    def __init__(self, envvar, required=True, default=None, **kwargs):
        if envvar and envvar in os.environ:
            default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(
            default=default, required=required, **kwargs
        )

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def add_compiler_args(parent_args, subparser):
    description = (
        "Detect tools like the compiler and pyton binaries, and "
        "set them up properly inside of the root project's "
        ".buckconfig.local"
    )
    parser = subparser.add_parser(
        "compiler",
        help="Sets up compiler + tools and configures buck to use them",
        description=description,
    )

    for args in parent_args:
        parser.add_argument(args.pop("name"), **args)


def add_fetch_args(parent_args, subparser):
    description = (
        "Fetch source for a package, and configure .buckconfig, "
        ".buckconfig.local, and BUCK files for third-party package "
        "managers"
    )
    parser = subparser.add_parser(
        "fetch",
        help="Fetches source and configures buck for a vendored library",
        description=description,
    )

    for args in parent_args:
        parser.add_argument(args.pop("name"), **args)

    parser.add_argument(
        "--use-python2",
        action="store_true",
        default=False,
        help="Whether python2 should be used",
    )
    parser.add_argument(
        "--python2-virtualenv",
        action=EnvDefault,
        required=True,
        default="virtualenv --python=python2.7",
        envvar="BUCKIT_PY2_VIRTUALENV",
        help=(
            "The python2 virtualenv command to use. Can be set with "
            "BUCKIT_PY2_VIRTUALENV environment variable"
        )
    )
    parser.add_argument(
        "--python2-virtualenv-root",
        action=EnvDefault,
        required=True,
        default="node_modules/__py2_virtualenv",
        envvar="BUCKIT_PY2_VIRTUALENV_ROOT",
        help="The directory to setup a virtualenv in"
    )
    parser.add_argument(
        "--use-python3",
        action="store_true",
        default=True,
        help="Whether python3 should be used",
    )
    parser.add_argument(
        "--python3-virtualenv",
        action=EnvDefault,
        required=True,
        default="virtualenv",
        envvar="BUCKIT_PY3_VIRTUALENV",
        help=(
            "The python3 virtualenv command to use. Can be set with "
            "BUCKIT_PY3_VIRTUALENV environment variable"
        )
    )
    parser.add_argument(
        "--python3-virtualenv-root",
        action=EnvDefault,
        required=True,
        default="node_modules/__py3_virtualenv",
        envvar="BUCKIT_PY3_VIRTUALENV_ROOT",
        help="The directory to setup a virtualenv in"
    )
    parser.add_argument(
        "--virtualenv-use-proxy-vars",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--package",
        action=EnvDefault,
        required=True,
        envvar="npm_package_name",
        help=(
            "The package to configure. Otherwise, pulled from the "
            "npm_package_name environment variable"
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=("Whether to force a fetch of the source")
    )


def add_buckconfig_args(parent_args, subparser):
    description = (
        "Configures .buckconfig and .buckconfig.local to have knowledge of "
        "all cells specified in package.json. Should not be run inside "
        "of individual package roots"
    )
    parser = subparser.add_parser(
        "buckconfig",
        help="Reconfigure .buckconfig and .buckconfig.local",
        description=description
    )

    for args in parent_args:
        parser.add_argument(args.pop("name"), **args)


def add_system_args(parent_args, subparser):
    description = (
        "Installs system packages required for all or some packages. Also "
        "configures buck to use system packages"
    )
    parser = subparser.add_parser(
        "system",
        help="Install system packages, and configure buck to use them",
        description=description,
    )

    for args in parent_args:
        parser.add_argument(args.pop("name"), **args)

    parser.add_argument(
        "--no-install-packages",
        help=(
            "If set, don't actually install packages specified in "
            "package.json files"
        ),
        action="store_false",
        dest="install_packages",
        default=True,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--use-system-for-all",
        help=(
            "If set, configure buckit to always use system specs if "
            "available. This is done by setting buckit.use_system_for_all "
            "in .buckconfig.local, and propagating it"
        ),
        action="store_true",
        dest="use_system_for_all",
    )
    group.add_argument(
        "--use-vendored-for-all",
        help=(
            "If set, configure buckit to always use vendored packages if "
            "available. This is done by setting buckit.use_system_for_all "
            "to false in .buckconfig.local"
        ),
        action="store_false",
        dest="use_system_for_all",
    )
    group.add_argument(
        "--use-system-for-cells",
        help=(
            "If set, configure buckit to only use system libraries for "
            "provided cells (comma delimited)"
        ),
        default="",
    )
    parser.set_defaults(use_system_for_all=None)


def parse_args(argv):
    description = dedent(
        """
    Automatically configure Buck and build third party libraries for
    easier C++ development"""
    )
    parser = argparse.ArgumentParser(description=description)

    parent_options = [
        {
            "name": "--log-level",
            "default": "info",
            "choices": sorted(log_levels.keys()),
            "action": EnvDefault,
            "required": True,
            "envvar": "BUCKIT_LOG_LEVEL",
        },
        {
            "name": "--node-modules",
            "default": "node_modules",
            "help": "Where yarn installs modules to",
        }
    ]
    subparser = parser.add_subparsers(dest="selected_action")
    add_buckconfig_args(copy.deepcopy(parent_options), subparser)
    add_compiler_args(copy.deepcopy(parent_options), subparser)
    add_fetch_args(copy.deepcopy(parent_options), subparser)
    add_system_args(copy.deepcopy(parent_options), subparser)

    return parser, parser.parse_args(argv)


def get_root_path(node_modules):
    # If we're in a post install event, then we
    # are inside of the package's root, not the main
    # project
    try:
        if os.environ.get('npm_lifecycle_event') == 'postinstall':
            start_path = os.path.split(os.getcwd())[0]
        else:
            start_path = os.getcwd()
        return configure_buck.find_project_root(start_path, node_modules)
    except BuckitException as e:
        logging.info(str(e))
        return os.getcwd()


def main(argv):
    parser, args = parse_args(argv)

    formatting.configure_logger(level=log_levels[args.log_level])
    ret = 0
    should_configure_buck = False
    project_root = get_root_path(args.node_modules)

    if args.selected_action == 'buckconfig':
        should_configure_buck = True
    elif args.selected_action == 'fetch':
        ret = fetch.fetch_package(
            project_root=project_root,
            node_modules=args.node_modules,
            package=args.package,
            use_python2=args.use_python2,
            python2_virtualenv=args.python2_virtualenv,
            python2_virtualenv_root=args.python2_virtualenv_root,
            use_python3=args.use_python3,
            python3_virtualenv=args.python3_virtualenv,
            python3_virtualenv_root=args.python3_virtualenv_root,
            virtualenv_use_proxy_vars=args.virtualenv_use_proxy_vars,
            force=args.force,
        )
        if ret == 0:
            should_configure_buck = True
    elif args.selected_action == 'compiler':
        ret = compiler.configure_compiler(project_root=project_root)
        if ret == 0:
            should_configure_buck = True
    elif args.selected_action == 'system':
        ret = use_system.use_system_packages(
            project_root=project_root,
            node_modules=args.node_modules,
            install_packages=args.install_packages,
            use_system_for_all=args.use_system_for_all,
            system_cells=filter(None, args.use_system_for_cells.split(',')),
        )
        if ret == 0:
            should_configure_buck = True
    else:
        parser.print_help()

    if should_configure_buck:
        ret = configure_buck.configure_buck_for_all_packages(
            project_root=project_root,
            node_modules=args.node_modules,
        )

    sys.exit(ret)


if __name__ == '__main__':
    main(sys.argv[1:])
