load("@bazel_skylib//lib:partial.bzl", "partial")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/facebook:python_wheel_overrides.bzl", "python_wheel_overrides")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")

# Container for values which have regular and platform-specific parameters.
_PlatformParam = provider(fields = [
    "value",
    "platform_value",
])

def _extract_source_name(src):
    """ Takes a string of the format foo=bar, and returns bar """
    parts = src.split("=")
    if len(parts) != 2:
        fail("generated source target {} is missing `=<name>` suffix".format(src))
    return parts[1]

def _get_parsed_source_name(src):
    """
    Get the filename for a `src`

    Args:
        src: Either a `RuleTarget`, or a string representing a filename

    Returns:
        Either the original source, or the filename, extracted from the target name.
    """
    rule_name = getattr(src, "name", None)
    if rule_name != None:
        return _extract_source_name(rule_name)
    else:
        return src

def _get_source_name(src):
    """
    Gets the filename for a `src`.

    Example:
        get_source_name("//foo:bar=path/to/baz.cpp") returns "path/to/baz.cpp",
        get_source_name("foo/bar/baz.cpp") returns "foo/bar/baz.cpp"

    Args:
        src: Either a filename, or, if a target, the bit after `=` from a
             custom rule.
    """
    if src[0] in "/:":
        return _extract_source_name(src)
    else:
        return src

def _convert_external_build_target(target, platform = None, lang_suffix = ""):
    """
    Convert a raw external_dep target to a buck label

    Args:
        target: The external_dep string or tuple
        platform: The platform to use when normalizing the target
        lang_suffix: Used when converting the target

    Returns:
        A buck label for the provided raw external_dep style target
    """

    return target_utils.target_to_label(
        src_and_dep_helpers.normalize_external_dep(target, lang_suffix = lang_suffix),
        platform = platform,
    )

def _convert_build_target(base_path, target, platform = None):
    """
    Convert the given raw target string (one given in deps) to a buck label

    Args:
        base_path: The package to use if the target string is relative
        target: The raw target string that should be normalized
        platform: The platform to use when parsing the dependency, if applicable

    Returns:
        A buck label for the provided raw target
    """

    return target_utils.target_to_label(
        target_utils.parse_target(target, default_base_path = base_path),
        platform = platform,
    )

def _convert_source(base_path, src):
    """
    Convert a source, which may refer to an in-repo source or a rule that generates it, to a buck label

    Args:
        base_path: The package that should be used when parsing relative labels
        src: A source path or a target

    Returns:
        A fully qualified buck label or a source path as a string
    """

    # TODO: This can probably actually support other repos
    if src.startswith(("//", ":")):
        target = target_utils.parse_target(src, default_base_path = base_path)
        if target.repo != None:
            fail("Expected root repository only for {} got {}".format(src, target))
        return target_utils.target_to_label(target)
    else:
        return src

def _convert_source_list(base_path, srcs):
    """
    Runs convert_source on a list of sources

    Args:
        base_path: The package that should be used when parsing relative labels
        srcs: A list of source paths or source labels to convert

    Returns:
        A list of fully qualified buck labels or source paths as strings
    """
    return [_convert_source(base_path, src) for src in srcs]

def _convert_source_map(base_path, srcs):
    """
    Converts a mapping of destination path -> source path / source target to a mapping of destination path -> source path / fully qualified target

    Args:
        base_path: The package that should be used when parsing relative labels
        srcs: A mapping of destination path -> source path / source target

    Returns:
        A mapping of the original name to a full buck label / source path
    """
    converted = {}
    for k, v in srcs.items():
        # TODO(pjameson, agallagher): We have no idea why this is here...
        name = _get_source_name(k)
        if name in converted:
            fail('duplicate name "{}" for "{}" and "{}" in source map'.format(name, v, converted[name]))
        converted[name] = _convert_source(base_path, v)
    return converted

def _parse_source(base_path, src):
    """
    Parse a source that can be either a label, or a source path into either a relative path, or a rule target struct

    Args:
        base_path: The package that should be used when parsing relative labels
        src: A source path or a target

    Returns:
        Either a rule target struct (if src was a build target), otherwise the original
        src string
    """
    if src.startswith(("//", ":", "@/")):
        return target_utils.parse_target(src, default_base_path = base_path)
    return src

def _parse_source_list(base_path, srcs):
    """
    Parse list of sources that can be either labels, or source paths into either relative paths, or rule target structs

    Args:
        base_path: The package that should be used when parsing relative labels
        src: A list of source paths or targets as strings

    Returns:
        A list of rule target structs, or the original source strings
    """
    return [_parse_source(base_path, src) for src in srcs]

def _parse_source_map(base_path, raw_srcs):
    """
    Parse the given map of source names to paths.

    Args:
        base_path: The package that should be used when parsing relative labels
        raw_srcs: A dictionary of destination paths -> source paths or labels

    Returns:
        A mapping for destination paths to either source paths or build target structs
    """

    return {name: _parse_source(base_path, src) for name, src in raw_srcs.items()}

def _format_platform_param(value):
    """
    Takes a value or callable and constructs a list of 'platform' tuples for buck to consume

    Args:
        value: Either a "partial" struct (from skylib) or a value. If a partial, it
               will be called for each platform and compiler available, and the result
               used. If a value, it will just be assigned for each combination.

    Returns:
        A list of (<buck platform regex>, <value>) tuples.
    """
    out = []
    is_partial = hasattr(value, "function")
    for platform in platform_utils.get_platforms_for_host_architecture():
        for _compiler in compiler.get_supported_compilers():
            result = partial.call(value, platform, _compiler) if is_partial else value
            if result:
                # Buck expects the platform name as a regex, so anchor it.
                # re.escape is not supported in skylark, however there should not be
                # any collisions in the names we have selected.
                buck_platform = platform_utils.to_buck_platform(platform, _compiler)
                out.append(("^{}$".format(buck_platform), result))
    return out

def _format_deps(deps, platform = None):
    """
    Takes a list of RuleTarget structs, and returns a new list of buck labels for the given platform
    """

    return [target_utils.target_to_label(d, platform = platform) for d in deps]

def __convert_auxiliary_deps(platform, deps):
    """
    Convert a list of dependencies and versions to a list of potentially versioned RuleTarget struts

    Args:
        platform: The platform to get auxilliary deps for
        deps: A list of (`RuleTarget`, version) tuples where version is either None
              or a string that should be found in the third-party config for this
              third party RuleTarget

    Returns:
        A list of RuleTarget structs, with adjusted base paths if the original
        RuleTarget/version combination was found in the auxiliary_deps section of the
        third-party configuration
    """

    # Load the auxiliary version list from the config.
    config = third_party.get_third_party_config_for_platform(platform)
    aux_versions = config["build"]["auxiliary_versions"]

    processed_deps = []

    for dep, vers in deps:
        # If the parsed version for this project is listed as an
        # auxiliary version in the config, then redirect this dep to
        # use the alternate project name it's installed as.
        proj = paths.basename(dep.base_path)
        if vers != None and vers in aux_versions.get(proj, []):
            dep = target_utils.RuleTarget(
                repo = dep.repo,
                base_path = dep.base_path + "-" + vers,
                name = dep.name,
            )

        processed_deps.append(dep)

    return processed_deps

def __format_platform_deps_gen(deps, deprecated_auxiliary_deps, platform, _):
    pdeps = deps

    # Auxiliary deps support.
    if deprecated_auxiliary_deps:
        pdeps = __convert_auxiliary_deps(platform, pdeps)

    # Process PyFI overrides
    if python_wheel_overrides.should_use_overrides():
        if platform in python_wheel_overrides.PYFI_SUPPORTED_PLATFORMS:
            pdeps = [
                python_wheel_overrides.PYFI_OVERRIDES.get(d.base_path, d)
                for d in pdeps
            ]

    return _format_deps(pdeps, platform = platform)

def _format_platform_deps(deps, deprecated_auxiliary_deps = False):
    """
    Takes a map of fbcode platform names to lists of deps and converts to
    an output list appropriate for Buck's `platform_deps` parameter.

    Also add override support for PyFI migration - T22354138

    Args:
        deps: A list of `RuleTarget` structs if deprecated_auxiliary_deps is False
              or a list of (`RuleTarget`, version_string|None) if
              deprecated_auxiliary_deps is True
        deprecated_auxiliary_deps: If True, modify dependencies based on third-party
                                   configuration, otherwise do not

    Returns:
        A list of (buck platform regex, [target labels])
    """
    return _format_platform_param(
        partial.make(__format_platform_deps_gen, deps, deprecated_auxiliary_deps),
    )

def _format_all_deps(deps, platform = None):
    """
    Formats a list of `RuleTarget` structs for both `deps` and `platform_deps`

    Args:
        deps: A list of `RuleTarget` structs
        platform: If provided, the platform to use for third-party dependencies. These
                  dependencies will then be added to the `deps` list, rather than
                  `platform_deps`. If None, `platform_deps` will be populated with
                  third party dependencies for all platforms

    Returns:
        A tuple of ([buck labels], [(buck platform regex, [buck labels])]). The first
        entry should be used for `deps`, the second one for `platform_deps` in cxx*
        rules.
    """

    out_deps = [
        target_utils.target_to_label(d)
        for d in deps
        if not third_party.is_tp2_target(d)
    ]
    out_platform_deps = []

    # If we have an explicit platform (as is the case with tp2 projects),
    # we can pass the tp2 deps using the `deps` parameter.
    if platform != None:
        out_deps.extend([
            target_utils.target_to_label(d, platform = platform)
            for d in deps
            if third_party.is_tp2_target(d)
        ])
    else:
        out_platform_deps = _format_platform_deps(
            [d for d in deps if third_party.is_tp2_target(d)],
        )

    return out_deps, out_platform_deps

def _normalize_external_dep(raw_target, lang_suffix = "", parse_version = False):
    """
    Normalize the various ways users can specify an external dep into a RuleTarget

    Args:
        raw_target: The string, tuple, etc (see target_utils.parse_external_dep)
        lang_suffix: The language suffix that should be added (or not)
        parse_version: Whether the version should be returned from e.g. tuples

    Returns:
        Either a RuleTarget if parse_version is False, or a (RuleTarget, version_string)
        if parse_version is True
    """

    parsed, version = (
        target_utils.parse_external_dep(
            raw_target,
            lang_suffix = lang_suffix,
        )
    )

    return parsed if not parse_version else (parsed, version)

def _format_source(src, platform = None):  # type: (Union[str, RuleTarget], str) -> str
    """
    Converts a 'source' to a string that can be used by buck native rules

    Args:
        src: Either a string (for a source file), or a RuleTarget that needs converted to a label
        platform: The platform to use to convert RuleTarget objects

    Returns:
        A string with either the source path, or a full buck label
    """

    if target_utils.is_rule_target(src):
        if src.repo != None and platform == None:
            fail("Invalid RuleTarget ({}) and platform ({}) provided".format(src, platform))
        return target_utils.target_to_label(src, platform = platform)

    return src

def _format_source_map_partial(tp2_srcs, platform, _):
    return {
        name: _format_source(src, platform = platform)
        for name, src in tp2_srcs.items()
    }

def _format_source_map(srcs):
    """
    Converts a map that is used by 'srcs' to a map that buck can use natively.

    Args:
        srcs: A map of file location -> string (filename) or RuleTarget

    Returns:
        A `PlatformParam` struct that contains both platform and non platform
        sources in formats that buck understands natively (map of file location ->
        buck label / source file)
    """

    # All path sources and fbcode source references are installed via the
    # `srcs` parameter.
    out_srcs = {}
    tp2_srcs = {}
    for name, src in srcs.items():
        if third_party.is_tp2_src_dep(src):
            tp2_srcs[name] = src
        else:
            # All third-party sources references are installed via `platform_srcs`
            # so that they're platform aware.
            out_srcs[name] = _format_source(src)

    out_platform_srcs = (
        src_and_dep_helpers.format_platform_param(
            partial.make(_format_source_map_partial, tp2_srcs),
        )
    )

    return _PlatformParam(platform_value = out_platform_srcs, value = out_srcs)

def _restrict_repos(deps, repos = [
    None,
    "fbcode",
    "third-party",
]):
    """
    Emit an error if any of the deps do not come from the given list of allowed
    repos.
    """
    for dep in deps:
        if dep.repo not in repos:
            fail('dep on restricted repo {}: "{}"'
                .format(dep.repo, target_utils.target_to_label(dep)))

def _without_platforms(platform_param):
    """
    Return the non-platform specific portion of `PlatformParam`

    Fail if it contains any platform-specific values

    Args:
        platform_param: A `PlatformParam` struct

    Returns:
        Whatever is in the non-platform-specific part of the struct
    """
    if platform_param.platform_value:
        fail("unexpected 'platform_value' in {}")
    return platform_param.value

src_and_dep_helpers = struct(
    PlatformParam = _PlatformParam,
    convert_build_target = _convert_build_target,
    convert_external_build_target = _convert_external_build_target,
    convert_source = _convert_source,
    convert_source_list = _convert_source_list,
    convert_source_map = _convert_source_map,
    extract_source_name = _extract_source_name,
    format_all_deps = _format_all_deps,
    format_deps = _format_deps,
    format_platform_deps = _format_platform_deps,
    format_platform_param = _format_platform_param,
    format_source = _format_source,
    format_source_map = _format_source_map,
    get_parsed_source_name = _get_parsed_source_name,
    get_source_name = _get_source_name,
    normalize_external_dep = _normalize_external_dep,
    parse_source = _parse_source,
    parse_source_list = _parse_source_list,
    parse_source_map = _parse_source_map,
    restrict_repos = _restrict_repos,
    without_platforms = _without_platforms,
)
