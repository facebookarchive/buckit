load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")

def _convert_blob_with_macros(blob, platform = None):
    """
    Replace common placeholders in flags, cmds of genrules, etc

    Currently this just replaces @/third-party: and @/third-party-tools:

    Args:
        blob: The blob to convert
        platform: Used to replace things like @/third-party: with the right platform
                  path.

    Returns:
        A fully interpolated string.
    """
    return third_party.replace_third_party_repo(blob, platform = platform)

def _convert_args_with_macros(blobs, platform = None):
    """
    Replace common placeholders in flags, cmds of genrules, etc

    Currently this just replaces @/third-party: and @/third-party-tools:

    Args:
        blobs: A list of blobs to convert
        platform: Used to replace things like @/third-party: with the right platform
                  path.

    Returns:
        A list of fully interpolated strings
    """
    return [_convert_blob_with_macros(b, platform = platform) for b in blobs]

def _convert_env_with_macros(env, platform = None):
    """
    Replace common placeholders in flags, cmds of genrules, etc

    Currently this just replaces @/third-party: and @/third-party-tools:

    Args:
        blobs: A dictionary of keys -> blobs to convert
        platform: Used to replace things like @/third-party: with the right platform
                  path.

    Returns:
        A dictionary of keys -> fully interpolated strings
    """
    return {
        k: _convert_blob_with_macros(v, platform = platform)
        for k, v in env.items()
    }

string_macros = struct(
    convert_args_with_macros = _convert_args_with_macros,
    convert_blob_with_macros = _convert_blob_with_macros,
    convert_env_with_macros = _convert_env_with_macros,
)
