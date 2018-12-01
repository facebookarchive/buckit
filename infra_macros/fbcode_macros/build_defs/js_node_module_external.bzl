load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:js_common.bzl", "js_common")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")

def js_node_module_external(name, node_module_name = None, deps = (), external_deps = (), visibility = None):
    """
    Creates a javascript rule that points at a third-party library

    This rule copies all files in the package into a `node_modules/<name>`
    directory based on `name` or `node_module_name`

    Args:
        name: The name of the rule to create. If `node_module_name` is not
              provided, this will be the name of the submodule underneath the
              genrule's output
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

    # External node modules package their entire project directory
    root = paths.join("node_modules", js_common.get_node_module_name(name, node_module_name))
    out_srcs = [
        (src, paths.join(root, src))
        for src in native.glob(["**/*"])
    ]

    js_common.generate_modules_tree(
        name,
        srcs = out_srcs,
        deps = js_common.combine_deps(deps, external_deps, platform),
        visibility = visibility,
    )
