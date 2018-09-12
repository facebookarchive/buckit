load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:js_common.bzl", "js_common")

def js_npm_module(
        name,
        srcs,
        node_module_name = None,
        deps = (),
        external_deps = (),
        visibility = None):
    """
    Creates a javascript rule that points at a third-party library

    This rule copies all files in srcs into a directory based on `name`
    or `node_module_name`

    Args:
        name: The name of the rule to create. If `node_module_name` is not
              provided, this will be the name of the submodule underneath the
              genrule's output
        srcs: A list of files to copy into the output directory
        node_module_name: The name of the subdirectory to put all source files
                          underneath.
        deps: A list of dependencies for this module. These should be
              javascript rules or genrules, as all files will be copied from
              the 'output' of these dependencies.
        external_deps: A list of `external_deps` style tuples. As with `deps`
                       these should either be genrules or javascript rules.
        visibility: The visibility of this rule and created rules. Defaults
                    to PUBLIC
    """

    visibility = get_visibility(visibility, name)
    platform = js_common.get_fbcode_platform()

    # NPM modules package their listed sources.
    root = paths.join("node_modules", js_common.get_node_module_name(name, node_module_name))
    out_srcs = [
        (src, paths.join(root, src_and_dep_helpers.get_source_name(src)))
        for src in sorted(srcs)
    ]

    js_common.generate_modules_tree(
        name,
        srcs = out_srcs,
        deps = js_common.combine_deps(deps, external_deps, platform),
        visibility = visibility,
    )
