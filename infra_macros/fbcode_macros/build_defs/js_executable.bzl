load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:third_party_config.bzl", "third_party_config")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:js_common.bzl", "js_common")

def _get_node_path(platform):
    """ Gets the path to the node binary to embed in jsars """
    path_template = "/usr/local/fbcode/{}/bin/node-{}"

    # TODO: OSS friendly
    node_version = third_party_config["platforms"][platform]["build"]["projects"].get("node", None)
    if node_version:
        return path_template.format(platform, node_version)
    else:
        return "node"

def js_executable(
        name,
        index,
        srcs = (),
        deps = (),
        external_deps = (),
        visibility = None):
    """
    Create an executable .jsar javascript rule

    Args:
        name: The name of the main rule
        index: The main entry point to the .jsar
        srcs: A list of source files or targets from custom_rules
        deps: A list of dependencies
        external_deps: A list of `external_deps` style tuples
        visibility: The visibility of this rule and created rules. Defaults
                    to PUBLIC
    """

    visibility = get_visibility(visibility, name)

    # Use the default platform for all of js rules
    platform = js_common.get_fbcode_platform()
    package = native.package_name()

    js_common.generate_modules_tree(
        name = name + "-modules",
        srcs = [(src, paths.join(package, src)) for src in srcs],
        deps = js_common.combine_deps(deps, external_deps, platform),
        visibility = visibility,
    )

    cmd = " ".join([
        "$(exe //tools/make_par:buck_make_jsar)",
        "--node=" + _get_node_path(platform),
        "--platform=" + platform,
        "\"$OUT\"",
        paths.join(package, index),
        "$(location :{})".format(name + "-modules"),
    ])

    fb_native.genrule(
        name = name,
        out = name + ".jsar",
        cmd = cmd,
        executable = True,
        visibility = visibility,
    )
