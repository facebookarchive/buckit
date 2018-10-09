load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

def _extract_name_from_custom_rule(src):
    parts = src.split("=")
    if len(parts) != 2:
        fail("generated source target {} is missing `=<name>` suffix".format(src))
    return parts[1]

def _extract_source_name(src):
    """
    Gets the filename for a `src`.

    Example:
        extract_source_name("//foo:bar=path/to/baz.cpp") returns "path/to/baz.cpp",
        get_soruce_name("foo/bar/baz.cpp") returns "foo/bar/baz.cpp"

    Args:
        src: Either a filename, or, if a target, the bit after `=` from a
             custom rule.
    """
    if src[0] in "/:":
        return _extract_name_from_custom_rule(src)
    else:
        return src

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
    """
    converted = {}
    for k, v in srcs.items():
        # TODO(pjameson, agallagher): We have no idea why this is here...
        name = _extract_source_name(k)
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

src_and_dep_helpers = struct(
    convert_source = _convert_source,
    convert_source_list = _convert_source_list,
    convert_source_map = _convert_source_map,
    extract_source_name = _extract_source_name,
    parse_source = _parse_source,
    parse_source_list = _parse_source_list,
    parse_source_map = _parse_source_map,
)
