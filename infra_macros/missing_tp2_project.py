with allow_unsafe_import():
    import __builtin__
    import os
    import pipes
    import textwrap


def missing_tp2_project(name, platform, project):
    """
    Used in lieu of a rule for an otherwise missing project for the given
    platform to trigger an error at build time of the unsupported platform is
    used.
    """

    msg = (
        'ERROR: {}: project "{}" does not exist for platform "{}"'
        .format(name, project, platform))
    msg = os.linesep.join(textwrap.wrap(msg, 79, subsequent_indent='  '))
    __builtin__.cxx_genrule(
        name=name + '-error',
        out='out.cpp',
        cmd='echo {} 1>&2; false'.format(pipes.quote(msg)),
    )
    __builtin__.cxx_library(
        name=name,
        srcs=[":{}-error".format(name)],
        exported_headers=[":{}-error".format(name)],
        visibility=['PUBLIC'],
    )
