"""
`maybe_export_file()` is used to generate an `export_file()` for files in the
source repository referenced directly by an item such as `install_data()` or a
similar rule that can take a local file as input.

In order to use these files from the source repository, we need Buck to export
them (using `export_file()`, but for an user of the Buck language, that feels
like an implementation detail.

So we do it transparently from here, if we encounter a name that looks like a
local file name (more specifically, something that doesn't match a Buck rule,
which we detect by looking at whether it contains a `:`.

When generating an `export_file()` under the hood, we use a sigil prefix of
`_IMAGE_EXPORT_FILE__` for the Buck target name, in order to avoid possible
conflicts with targets defined by the user.
"""

load("@bazel_skylib//lib:types.bzl", "types")

def maybe_export_file(source):
    if source == None or not types.is_string(source) or ":" in source:
        return source
    buck_target_name = "_IMAGE_EXPORT_FILE__" + source
    if native.rule_exists(buck_target_name):
        return ":" + buck_target_name
    export_file(
        name = buck_target_name,
        src = source,
        visibility = ["//visibility:private"],
    )
    return ":" + buck_target_name
