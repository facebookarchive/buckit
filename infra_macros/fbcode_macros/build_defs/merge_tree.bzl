load("@bazel_skylib//lib:paths.bzl", _paths = "paths")
load("@fbcode_macros//build_defs:common_paths.bzl", "common_paths")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def merge_tree(
        base_path,
        name,
        paths,
        deps,
        visibility = None,
        labels = None):
    """
    Generate a rule which creates an output dir with the given paths merged
    with the merged directories of it's dependencies.
    """

    cmds = []

    for dep in sorted(deps):
        cmds.append('rsync -a $(location {})/ "$OUT"'.format(dep))

    paths = sorted(paths)

    for src in paths:
        src = src_and_dep_helpers.get_source_name(src)
        dst = _paths.join('"$OUT"', base_path, src)
        cmds.append("mkdir -p {}".format(_paths.dirname(dst)))
        cmds.append("cp {} {}".format(src, dst))

    fb_native.genrule(
        name = name,
        labels = labels or [],
        visibility = visibility,
        out = common_paths.CURRENT_DIRECTORY,
        srcs = paths,
        cmd = " && ".join(cmds),
    )
