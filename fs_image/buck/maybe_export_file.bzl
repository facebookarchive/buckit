load("@bazel_skylib//lib:types.bzl", "types")

def maybe_export_file(source):
    if source == None or not types.is_string(source) or ":" in source:
        return source
    export_file(
        name = source,
        visibility = ["//visibility:private"],
    )
    return ":" + source
