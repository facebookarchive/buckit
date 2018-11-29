"""
Methods related to creating mypy typing rules for python rules.

See http://mypy.readthedocs.io/en/latest/introduction.html for details
"""

load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_string")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")

def get_typing_config_target():
    """
    If set, use this tool to generate typing information for python-typecheck
    """
    return read_string("python", "typing_config", None)

def gen_typing_config_attrs(
        target_name,
        base_path = "",
        srcs = (),
        deps = (),
        typing = False,
        typing_options = "",
        labels = None,
        visibility = None):
    """
    Generate typing configs, and gather those for our deps

    Creates a genrule that copies all of the files from the -typing
    dependencies in `deps` into one directory, and optionally
    runs the typing tools on it.

    Args:
        target_name: The name of the target to create a config for
        base_path: The base_path (in dotted format) where
        srcs: A list of sources that should be passed to the typing tool
              if `typing` is True
        deps: A list of -typing dependencies whose sources should be copied
              into the 'out' directory
        typing: If true, run the typing config tool, else just generate an
                empty rule with the correct name (so that others can depend
                on this rule blindly by name)
        typing_options: Additional CLI options to pass to the typing tool
        visibility: If provided a list of visibilities for this rule

    Returns:
        Returns a dictionary of attributes -> values that can be passed to a
        native.genrule(), or to a 'Rule' object. 'Rule' logic will eventually be
        deprecated, at which point this method will go away
    """
    _ignore = visibility

    # TODO: Might make sense to have this combination logic
    #       as something native in buck to also let it detect
    #       duplicate files
    typing_config = get_typing_config_target()
    name = target_name + "-typing"
    cmds = ['mkdir -p "$OUT"']
    for dep in deps:
        # Experimental has visibility restricted, just skip them
        if dep.startswith("//experimental"):
            continue

        # not in fbcode don't follow out ex: xplat//target
        if not dep.startswith("//") and not dep.startswith(":"):
            continue
        cmds.append(
            'rsync -a "$(location {}-typing)/" "$OUT/"'.format(dep),
        )

    if typing:
        src_prefix = base_path.replace(".", "/")
        file_name = paths.join(src_prefix, target_name)
        cmds.append("mkdir -p `dirname $OUT/{}`".format(file_name))

        # We should support generated sources at some pointa
        # If srcs is a dict then we should use the values
        if type(srcs) == type({}):
            srcs = srcs.values()

        srcs = [
            paths.join(
                src_prefix,
                # TODO: This logic exists, but it may not be
                #       correct unless the typing tool understands
                #       ':<target>'
                src if src[0] not in "@/:" else paths.basename(src),
            )
            for src in srcs
        ]
        cmd = "$(exe {}) part ".format(typing_config)
        if typing_options:
            cmd += '--options="{}" '.format(typing_options)
        cmd += "$OUT/{} {}".format(file_name, " ".join(srcs))
        cmds.append(cmd)

    attrs = {}
    attrs["name"] = name
    if labels != None:
        attrs["labels"] = labels

    # Maybe we can fix this in the future, but specific visibility rules
    # break typing rules from depending on each other
    attrs["visibility"] = get_visibility(None, name)

    # Directory name is arbitrary
    attrs["out"] = "root"
    attrs["cmd"] = "\n".join(cmds)
    return attrs

def gen_typing_config(
        target_name,
        base_path = "",
        srcs = (),
        deps = (),
        typing = False,
        typing_options = "",
        labels = None,
        visibility = None):
    """
    Generate typing configs, and gather those for our deps

    Creates a genrule that copies all of the files from the -typing
    dependencies in `deps` into one directory, and optionally
    runs the typing tools on it.

    Args:
        target_name: The name of the target to create a config for
        base_path: The base_path (in dotted format) where
        srcs: A list of sources that should be passed to the typing tool
              if `typing` is True
        deps: A list of -typing dependencies whose sources should be copied
              into the 'out' directory
        typing: If true, run the typing config tool, else just generate an
                empty rule with the correct name (so that others can depend
                on this rule blindly by name)
        typing_options: Additional CLI options to pass to the typing tool
        visibility: If provided a list of visibilities for this rule

    Returns:
        Nothing
    """
    attrs = gen_typing_config_attrs(
        srcs = srcs,
        base_path = base_path,
        target_name = target_name,
        typing = typing,
        typing_options = typing_options,
        labels = labels,
        visibility = visibility,
        deps = deps,
    )
    fb_native.genrule(**attrs)
