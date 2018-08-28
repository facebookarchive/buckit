def _extract_name_from_custom_rule(src):
    parts = src.split("=")
    if len(parts) != 2:
        fail("generated source target {} is missing `=<name>` suffix".format(src))
    return parts[1]

def _get_source_name(src):
    """
    Gets the filename for a `src`.

    Example:
        get_source_name("//foo:bar=path/to/baz.cpp") returns "path/to/baz.cpp",
        get_soruce_name("foo/bar/baz.cpp") returns "foo/bar/baz.cpp"

    Args:
        src: Either a filename, or, if a target, the bit after `=` from a
             custom rule.
    """
    if src[0] in "/:":
        return _extract_name_from_custom_rule(src)
    else:
        return src

src_and_dep_helpers = struct(
    get_source_name = _get_source_name,
)
