import json
import os
import logging
import shlex

from collections import namedtuple

from constants import PACKAGE_JSON
from helpers import BuckitException
from fetchers import PipFetcher, HttpTarballFetcher, GitFetcher

PythonSettings = namedtuple(
    'PythonSettings', [
        'use_python2',
        'use_python3',
        'python2_virtualenv_command',
        'python2_virtualenv_root',
        'python3_virtualenv_command',
        'python3_virtualenv_root',
    ]
)


def get_package_root(node_modules, package):
    """
    Finds the directory that the package.json is stored in for given package

    Args:
        node_modules: The absolute path to Yarn's node_modules directory
        package: The name of the package

    Returns: Absolute path to the package's root
    """
    return os.path.join(node_modules, package)


def get_fetcher_from_repository(package_name, package_root, python_settings):
    package_json = os.path.join(package_root, PACKAGE_JSON)

    with open(package_json, 'r') as fin:
        js = json.loads(fin.read())

    short_name = js.get('name').split('/')[-1]

    if 'repository' not in js:
        raise BuckitException(
            "The repository section is missing in {}", package_json)

    repository = js.get('repository')
    repo_type = repository.get("type", "")
    if 'pip_info' in repository:
        pip_info = repository.get('pip_info')
        dest_dir = os.path.join(
            package_root, pip_info.get("install_subdir", short_name)
        )
        return (
            PipFetcher(
                package_name,
                package_json,
                pip_info.get("pip2_package", ""),
                pip_info.get("pip2_version", ""),
                pip_info.get("pip3_package", ""),
                pip_info.get("pip3_version", ""),
                pip_info.get("main_rule", ""),
                pip_info.get("buck_deps", []),
                python_settings,
            ), dest_dir
        )
    elif repo_type == "git":
        dest_dir = os.path.join(package_root, short_name)
        return (
            GitFetcher(
                package_name,
                package_json,
                repository.get("url", ""),
                repository.get("commit", None),
                repository.get("tag", None),
            ), dest_dir
        )
    elif repo_type == "tarball":
        dest_dir = os.path.join(package_root, short_name)
        return (
            HttpTarballFetcher(
                package_name,
                package_json,
                repository.get("url", ""),
                repository.get("sha256", ""),
            ), dest_dir
        )
    else:
        raise BuckitException(
            "repository.type in {} must be either 'git', 'tarball', or 'pip'",
            package_json)


def fetch_package(
    project_root, node_modules, package, use_python2, python2_virtualenv,
    python2_virtualenv_root, use_python3, python3_virtualenv,
    python3_virtualenv_root, virtualenv_use_proxy_vars, force
):
    node_modules = os.path.realpath(os.path.join(project_root, node_modules))
    package_root = get_package_root(node_modules, package)

    if not os.path.isabs(python2_virtualenv_root):
        python2_virtualenv_root = os.path.join(
            project_root, python2_virtualenv_root
        )
    if not os.path.isabs(python3_virtualenv_root):
        python3_virtualenv_root = os.path.join(
            project_root, python3_virtualenv_root
        )

    python_settings = PythonSettings(
        use_python2,
        use_python3,
        shlex.split(python2_virtualenv),
        python2_virtualenv_root,
        shlex.split(python3_virtualenv),
        python3_virtualenv_root,
    )
    fetcher, dest_dir = get_fetcher_from_repository(
        package, package_root, python_settings
    )

    use_proxy = {
        PipFetcher: virtualenv_use_proxy_vars,
    }

    if fetcher.should_fetch(dest_dir, force):
        fetcher.fetch(
            project_root,
            dest_dir,
            use_proxy=use_proxy.get(type(fetcher), True))
    else:
        logging.info(
            "{bold}Destination directory %s already exists, not fetching. "
            "Use --force to force a fetch of the source{clear}", dest_dir
        )
    return 0
