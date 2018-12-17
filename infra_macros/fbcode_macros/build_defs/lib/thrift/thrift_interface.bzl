"""
Common methods used to implement a 'language' in the thrift_library macro
"""

load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool")

def _default_get_compiler_command(compiler, compiler_args, includes, additional_compiler):
    cmd = []
    cmd.append("$(exe {})".format(compiler))
    cmd.extend(compiler_args)
    cmd.append("-I")
    cmd.append(
        "$(location {})".format(includes),
    )
    if read_bool("thrift", "use_templates", True):
        cmd.append("--templates")
        cmd.append("$(location {})".format(config.get_thrift_templates()))
    cmd.append("-o")
    cmd.append('"$OUT"')

    # TODO(T17324385): Work around an issue where dep chains of binaries
    # (e.g. one binary which delegates to another when it runs), aren't
    # added to the rule key when run in `genrule`s.  So, we need to
    # explicitly add these deps to the `genrule` using `$(exe ...)`.
    # However, since the implemenetation of `--python-compiler` in thrift
    # requires a single file path, and since `$(exe ...)` actually expands
    # to a list of args, we ues `$(query_outputs ...)` here and just append
    # `$(exe ...)` to the end of the command below, in a comment.
    if additional_compiler:
        cmd.append("--python-compiler")
        cmd.append('$(query_outputs "{}")'.format(additional_compiler))
    cmd.append('"$SRCS"')

    # TODO(T17324385): Followup mentioned in above comment.
    if additional_compiler:
        cmd.append("# $(exe {})".format(additional_compiler))

    return " ".join(cmd)

thrift_interface = struct(
    default_get_compiler_command = _default_get_compiler_command,
)
