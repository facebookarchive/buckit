#!/usr/bin/env python3
'''
This runs with system Python, so stick to the standard library for <= 3.6

Run this script with no arguments to re-generate the test RPM repos.

Our goal is to test repo snapshotting. An input achieving good coverage would:
 - provide a history with several time-steps,
 - contain potentially related RPM repos that change between time-steps,
 - contain different packages, as well as varying versions of the same package,
 - have packages that occur in the same or different versions across repos,
 - include multiple architectures.

This script builds such a history -- sibling directories like `x84_64`
enumerate the tested architectures.  These outputs are committed to version
control so that the test / CI environment need not provide RPM tooling.
'''
import os
import shutil
import subprocess
import tempfile
import textwrap

from typing import Dict, List, NamedTuple


class Rpm(NamedTuple):
    name: str
    version: str
    release: str

    def spec(self):
        return textwrap.dedent('''\
        Summary: The "{name}" package.
        Name: rpm-test-{name}
        Version: {version}
        Release: {release}
        License: BSD
        Group: Facebook/Script
        Vendor: Facebook, Inc.
        Packager: somebody@example.com

        %description
        %install
        mkdir -p "$RPM_BUILD_ROOT"/usr/share/rpm_test
        echo '{name} {version} {release}' \
          > "$RPM_BUILD_ROOT"/usr/share/rpm_test/{name}.txt
        %files
        /usr/share/rpm_test/{name}.txt
        ''').format(**self._asdict())


class Repo(NamedTuple):
    rpms: List[Rpm]


# The array index is the step number, modeling the passage of time.
#
#  - If a repo has a value of `None`, we will delete this repo, asserting
#    that it existed in the prior timestamp.
#  - If a repo value is a string, it is an alias to another existing repo,
#    represented by a symlink on disk.
REPO_CHANGE_STEPS = [
    {
        'bunny': Repo([Rpm('carrot', '2', 'rc0')]),
        'cat': Repo([Rpm('milk', '2.71', '8'), Rpm('mice', '0.1', 'a')]),
        'dog': Repo([
            Rpm('milk', '1.41', '42'),  # Different version than in `cat`
            Rpm('mice', '0.1', 'a'),
            Rpm('carrot', '2', 'rc0'),  # Same version as in `bunny`
        ]),
        'puppy': 'dog',
    },
    {
        'bunny': None,
        'cat': Repo([Rpm('milk', '3.14', '15')]),  # New version
        'dog': Repo([Rpm('bone', '5i', 'beef'), Rpm('carrot', '2', 'rc0')]),
        'kitty': 'cat',
    },
]


def build_rpm(package_dir: str, arch: str, rpm: Rpm) -> str:
    'Returns the filename of the built RPM.'
    with tempfile.TemporaryDirectory(dir=package_dir) as td, \
            tempfile.NamedTemporaryFile() as tf:
        tf.write(rpm.spec().encode())
        tf.flush()
        subprocess.run(
            [
                # Has to be an absolute path thanks to @phild >:-/
                '/usr/bin/rpmbuild', '-bb', '--target', arch,
                '--buildroot', os.path.join(td, 'build'), tf.name,
            ],
            env={'HOME': os.path.join(td, 'home')},
            check=True,
        )
        # `rpmbuild` has a non-configurable output layout, so
        # we'll move the resulting rpm into our package dir.
        rpms_dir = os.path.join(td, 'home/rpmbuild/RPMS', arch)
        rpm_name, = os.listdir(rpms_dir)
        os.rename(
            os.path.join(rpms_dir, rpm_name),
            os.path.join(package_dir, rpm_name),
        )
        return rpm_name


def make_repo_steps(
    out_dir: str, repo_change_steps: List[Dict[str, Repo]], arch: str,
):
    # When an RPM occurs in two different repos, we want it to be
    # bit-identical (otherwise, the snapshot would see a `mutable_rpm`
    # error).  This means never rebuilding an RPM that was previously seen.
    # The paths are relative to `out_dir`.
    rpm_to_path = {}
    # The repos that exist at the current step.
    repos = {}
    for step, repo_changes in enumerate(repo_change_steps):
        for repo_name, repo in repo_changes.items():
            if repo is None:
                del repos[repo_name]
            else:
                repos[repo_name] = repo
        step_dir = os.path.join(out_dir, str(step))
        os.makedirs(step_dir)
        for repo_name, repo in repos.items():
            repo_dir = os.path.join(step_dir, repo_name)
            if isinstance(repo, str):  # Symlink to another repo
                assert repo in repos
                os.symlink(repo, repo_dir)
                continue
            # Each repo's package dir is different to exercise the fact
            # that the same file's location may differ across repos.
            package_dir = os.path.join(repo_dir, f'{repo_name}-pkgs')
            os.makedirs(package_dir)
            for rpm in repo.rpms:
                prev_path = rpm_to_path.get(rpm)
                if prev_path:
                    os.symlink(
                        os.path.join('../../..', prev_path),
                        os.path.join(package_dir, os.path.basename(prev_path)),
                    )
                else:
                    rpm_to_path[rpm] = os.path.join(
                        str(step), repo_name, os.path.basename(package_dir),
                        build_rpm(package_dir, arch, rpm),
                    )
            # Now that all RPMs were built, we can generate the Yum metadata
            subprocess.run(['createrepo', repo_dir], check=True)


if __name__ == '__main__':
    # This wouldn't work from a PAR, but it's OK in a system-Python script.
    base_dir = os.path.dirname(os.path.realpath(__file__))
    td = tempfile.mkdtemp(dir=base_dir)  # dir= to stay on one filesystem
    try:
        for arch in ['x86_64', 'aarch64']:
            make_repo_steps(os.path.join(td, arch), REPO_CHANGE_STEPS, arch)
        dest_path = os.path.join(base_dir, 'repos')
        shutil.rmtree(dest_path)  # A prior directory always exists here.
        os.rename(td, dest_path)
    except BaseException:  # Clean up even on Ctrl-C
        shutil.rmtree(td)
        raise
