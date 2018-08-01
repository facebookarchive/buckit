load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:types.bzl", "types")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:common_paths.bzl", "get_gen_path")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")

_ERROR_BAD_GEN_FILES = ("custom_rule(): {}:{}: output_gen_files and " +
                        "output_bin_files must be lists of filenames, got {}")

_ERROR_BAD_BUILD_ARGS = ("custom_rule(): {}:{}: build_args must be a string " +
                         "or None, got {}")

_ERROR_BAD_OUTPUT_PATH = ("custom_rule(): {}:{}: output file {} cannot " +
                          "contain '..'")

_ERROR_OUT_NOT_SPECIFIED = ("custom_rule(): {}:{}: neither output_gen_files " +
                            "nor output_bin_files were specified")

path_sep = ";" if native.host_info().os.is_windows else ":"

def _get_output_dir(name):
    """ Return the name of the main genrule's output directory """
    return name + "-outputs"

def _get_project_root_from_gen_dir():
    """
    Gets the project root relative to the buck-out gen directory

    NOTE: This is fragile when dealing with multiple cells or when buck-out
          is outside of the main repository. This can also lead to non-hermetic
          builds depending on how the information is used. It will eventually
          be removed after all legacy features no longer depend on it.

    Returns: Something like '../../../' if the buck-out directory is configured
             to buck-out/dev. This can be appended to $GEN_DIR in genrules
    """
    # paths.relativize doesn't work with things that traverse upward...
    return ".." + get_gen_path().count("/") * "/.."

def _create_main_rule(
        name,
        build_script_dep,
        build_args=None,
        tools=(),
        srcs=(),
        deps=(),
        strict=True,
        env=None,
        no_remote=False,
        build_script_visibility=None):

    package = native.package_name()

    out = _get_output_dir(name)
    fbcode_platform, buck_platform = platform_utils.get_fbcode_and_buck_platform_for_current_buildfile()
    fbcode_dir = paths.join("$GEN_DIR", _get_project_root_from_gen_dir())
    install_dir = '"$OUT"'

    # Build up a custom path using any extra tools specified by the
    # 'custom_rule'.
    new_path = []
    tool_bin_rules = []
    for tool in tools:
        tool_bin_rules.append(third_party.get_tool_bin_target(tool, fbcode_platform))
        tool_path = third_party.get_tool_path(tool, fbcode_platform)
        new_path.append(paths.join(fbcode_dir, tool_path, "bin"))
    new_path.append('"$PATH"')

    # Initially, create the output directory.
    cmd = 'mkdir -p "$OUT" && '

    # Setup the environment properly
    env = dict(env) if env else {}
    if not strict:
        env['FBCODE_DIR'] = fbcode_dir
    env['INSTALL_DIR'] = install_dir
    env['PATH'] = path_sep.join(new_path)
    env['FBCODE_BUILD_MODE'] = config.get_build_mode()
    env['FBCODE_BUILD_TOOL'] = 'buck'
    env['FBCODE_PLATFORM'] = fbcode_platform
    env['BUCK_PLATFORM'] = buck_platform
    env['SRCDIR'] = '"$SRCDIR"'

    # Add in the tool rules to the environment.  They won't be consumed by
    # the script/user, but they will affect the rule key.
    env['FBCODE_THIRD_PARTY_TOOLS'] = ':'.join([
        '$(location {})'.format(r)
        for r in tool_bin_rules
    ])
    cmd += (
        'env ' +
        ' '.join(['{}={}'.format(k, v) for k, v in sorted(env.items())]) +
        ' ')

    cmd += '$(exe {})'.format(third_party.replace_third_party_repo(build_script_dep, fbcode_platform))
    if not strict:
        cmd += " --fbcode_dir=" + fbcode_dir
    cmd += " --install_dir=" + install_dir

    if build_args:
        cmd += " " + third_party.replace_third_party_repo(build_args, fbcode_platform)

    # Some dependencies were not converted into $(location) macros. Buck
    # does not support dependencies for genrules since it is more
    # efficient if it can track exactly which outputs are used, but as
    # long as rules do not rely on the side effects of their
    # dependencies and find their output properly, adding an ignored
    # $(location) macro should be almost equivalent to a dep.
    if deps:
        # This warning will be useful in the future, but is spammy right now
        #  print((
        #      "{}:{} has {} dependencies. These should be used directly in the " +
        #      "command, rather than added as explicit dependencies").format(
        #          package, name, len(deps)))
        cmd += " #"
        for dep in deps:
            cmd += " $(location {})".format(
                third_party.replace_third_party_repo(dep, fbcode_platform))

    native.genrule(
        name=out,
        out=out,
        cmd=cmd,
        srcs=srcs,
        no_remote=no_remote,
    )
    return out

def _copy_genrule_output(genrule_target, out_genrule_name, out, visibility):
    """
    Creates a rule to address a single output from a genrule that creates multiple outputs

    Args:
        genrule_target: The original genrule target
        out_genrule_name: The name of the rule to be created that refers to a
                          single file
        out: The name of the file within the original genrule's output, which
             will also be used for the new rule's out parameter
    """
    if native.host_info().os.is_linux:
        cmd = ('mkdir -p `dirname "$OUT"` && ' +
               'cp -rlT "$(location {genrule_target})/{out}" "$OUT"')
    elif native.host_info().os.is_macos:
        cmd = ('mkdir -p `dirname "$OUT"` && ' +
               'ln "$(location {genrule_target})/{out}" "$OUT"')
    # TODO: Windows support
    else:
        fail("Unknown OS in custom_rule")

    native.genrule(
        name=out_genrule_name,
        out=out,
        cmd=cmd.format(genrule_target=genrule_target, out=out),
        visibility=visibility,
    )

def copy_genrule_output_file(name_prefix, genrule_target, filename, visibility):
    """
    Creates a genrule to copy a sub-file from inside of a genrule

    Args:
        name_prefix: The first part of the rule name to use
        genrule_target: The target that has output multiple files
        filename: The name of the file inside of the original genrule output
                  directory
        visibility: The visibility for the rule
    """
    out_name = name_prefix + "=" + filename
    visibility = get_visibility(visibility, out_name)
    _copy_genrule_output(genrule_target, out_name, filename, visibility)

def custom_rule(
        name,
        build_script_dep,
        build_args=None,
        output_gen_files=(),
        output_bin_files=(),
        tools=(),
        srcs=(),
        deps=(),
        strict=True,
        env=None,
        no_remote=False,
        visibility=None,
        ):
    """
    Creates rules to run a script and allow other rules to access that scripts outputs

    Under the hood this is similar to genrules in a lot of ways, but it can
    produce multiple outputs, and makes some environement variables available
    to users.

    Any arbitrary script may be used in a custom_rule (e.g. a buck_sh_binary),
    as long as the script accepts the flag --install_dir and puts the output
    files in that directory. The build tools will also pass the location of
    the fbcode/ root directory as --fbcode_dir, in case your script needs to
    reference other files within the fbcode/ tree (e.g data files). These two
    flags are also passed as environment variables (INSTALL_DIR and FBCODE_DIR)
    for convenience.

    Creates a main rule to run the script and for each output, creates a rule
    with the name `<name>=<output>` to refer to a specific file from the output

    Args:
        name: The name of the main rule, and the basis for derived rules
        build_script_dep: Dependent target that will produce build script or
                          executable. Generally either a python_binary or
                          a buck_sh_binary
        build_args: Arguments to pass to the build script. Third party place
                    holders will be interpolated here in addition to standard
                    buck string macros
        output_gen_files: List of files that will be generated by this rule,
                          relative to $INSTALL_DIR.
        output_bin_files: List of other files that will be generated by this
                          rule, relative to $INSTALL_DIR. This is deprecated
                          and will be removed in the future.
        tools: A list of third-party tools that are required. This is resolved
               using common logic in @fbcode_macros//build_defs:third_party.bzl.
               These tools' paths will be added to the FBCODE_THIRD_PARTY_TOOLS
               environment variable.
        srcs: Sources that are required by the build script. This works like
              normal buck genrule srcs, and these files are available relative
              to SRCDIR in the build script.
        deps: Deprecated. This is used to declare additional dependencies that
              the build script depends on implicitly. This should not be used
              and instead the dependency should either be in a string macro
              in build_args, or it should be in the srcs list. This may be
              deprecated in the future.
        strict: Runs the rule without access to the root of the repository via
                the FBCODE_DIR env var, or --fbcode_dir passed on the command
                line (defaults to False for now). This may be removed in the
                future, as it is unsafe to access files that are not explicitly
                listed in the srcs parameter or via a $(location ...) macro.
        env: A dictionary of environment variables to expand. $(location ...)
             macros and the like are expanded in values here.
        no_remote: This is a transitory property for some scripts that do not
                   work with distributed builds properly. It will be removed
                   in the future. Do not use this.
        visibility: If provided, override the visibility of this rule.
    """

    # Normalize visibility
    visibility = get_visibility(visibility, name)
    package = native.package_name()

    if not (types.is_list(output_gen_files) or types.is_tuple(output_gen_files)):
        fail(_ERROR_BAD_GEN_FILES.format(package, name, output_gen_files))

    if build_args != None and not types.is_string(build_args):
        # TODO(T30634665): Remove when we're at 100% skylark. unicode strings
        #                  muck up is_string
        if str(build_args) != build_args:
            fail(_ERROR_BAD_BUILD_ARGS.format(package, name, build_args))

    outs = list(output_gen_files) + list(output_bin_files)

    if not outs:
        fail(_ERROR_OUT_NOT_SPECIFIED.format(package, name))

    # Make sure output params don't escape install directory
    for out in outs:
        # TODO: Get split into paths()?
        if ".." in out.split("/"):
            fail(_ERROR_BAD_OUTPUT_PATH.format(package, name, out))

    # Add the main rule which runs the custom rule and stores its outputs in
    # a single directory
    main_rule_name = _create_main_rule(
        name=name,
        build_script_dep=build_script_dep,
        build_args=build_args,
        tools=tools,
        srcs=srcs,
        deps=deps,
        strict=strict,
        env=env,
        no_remote=no_remote,
        build_script_visibility=visibility)
    main_rule_target = ':' + main_rule_name

    # For each output, create a `=<out>` rule which pulls it from the main
    # output directory so that consuming rules can use use one of the
    # multiple outs.
    for out in outs:
        out_name = name + "=" + out
        _copy_genrule_output(main_rule_target, out_name, out, visibility)

    # When we just have a single output, also add a rule with the original
    # name which just unpacks the only listed output.  This allows consuming
    # rules to avoid the `=<out>` suffix.
    if len(outs) == 1:
        _copy_genrule_output(main_rule_target, name, outs[0], visibility)
    else:
        # Otherwise, use a dummy empty Python library to force runtime
        # dependencies to propagate onto all of the outputs of the custom rule.
        native.python_library(
            name=name,
            visibility=visibility,
            deps=[":{}={}".format(name, o) for o in outs],
        )
