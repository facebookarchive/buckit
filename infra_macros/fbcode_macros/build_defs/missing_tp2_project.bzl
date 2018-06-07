"""
Helper macros for rules that do not exist for a given platform
"""

load("@bazel_skylib//lib:shell.bzl", "shell")

_CMD_TEMPLATE = """echo {} | fold -s -w 70 | sed 's, *$,,' | awk 'NR == 1 {{ print $0 }} NR > 1 {{ printf("       %s\\n", $0) }}' 1>&2; exit 1"""

def missing_tp2_project(name, platform, project):
    """
    Rule to fail if a project is not available for a platform

    Used in lieu of a rule for an otherwise missing project for the given
    platform to trigger an error at build time of the unsupported platform is
    used.

    Args:
        name: The name of the rule within the project that is unavailable
        project: The high level name of the project that is unavailable
                  (e.g. "openssl", or "gflags")
        platform: The name of the platform that the project is unavailable for
    """
    msg = 'ERROR: {}: project "{}" does not exist for platform "{}"'.format(
        name, project, platform)
    error_rule = name + "-error"
    native.cxx_genrule(
        name=error_rule,
        out="out.cpp",
        cmd=_CMD_TEMPLATE.format(shell.quote(msg)),
    )
    native.cxx_library(
        name=name,
        srcs=[":" + error_rule],
        exported_headers=[":" + error_rule],
        visibility=["PUBLIC"],
    )
