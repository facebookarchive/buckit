load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")

def _get_fbcode_platform():
    """ JS rules don't use the build file path for platforms, return the default one instead """
    return platform_utils.get_platform_for_base_path("")

def _combine_deps(deps, external_deps, platform):
    """ Combines deps and external deps (for the current platform) into one list """
    return [
        third_party.replace_third_party_repo(dep, platform = platform)
        for dep in deps
    ] + [
        third_party.external_dep_target(dep, platform = platform)
        for dep in external_deps
    ]

def _generate_modules_tree(name, srcs, deps, visibility):
    """
    Creates a genrule that creates a directory tree that looks like a node_modules directory

    Args:
        name: The name of the new rule
        srcs: A list of tuples of the original source file, and where the source
              should reside in the tree,
        deps: A list of all resolved dependencies for the new rule
        visibility: The visibility of the rule
    """
    cmds = [
        'rsync -a $(location {})/ "$OUT"'.format(dep)
        for dep in deps
    ]

    dirs = {}
    files = []
    for raw_src, dst in srcs:
        src = src_and_dep_helpers.get_source_name(raw_src)
        dst = paths.join('"$OUT"', dst)
        files.append((src, dst))
        dirs[paths.dirname(dst)] = None

    cmds.append("mkdir -p " + " ".join(sorted(dirs.keys())))
    for src, dst in files:
        cmds.append("cp {} {}".format(src, dst))

    native.genrule(
        name = name,
        out = "modules",
        srcs = [s[0] for s in srcs],
        cmd = " && ".join(cmds),
        visibility = visibility,
    )

def _get_node_module_name(name, node_module_name):
    return name if node_module_name == None else node_module_name

js_common = struct(
    combine_deps = _combine_deps,
    generate_modules_tree = _generate_modules_tree,
    get_fbcode_platform = _get_fbcode_platform,
    get_node_module_name = _get_node_module_name,
)
