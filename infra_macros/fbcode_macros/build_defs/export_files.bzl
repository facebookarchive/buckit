"""
Quick function that re-exports files
"""

load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")

def export_files(files, visibility=None, mode="reference"):
    """ Takes a list of files, and exports each of them """
    visibility = get_visibility(visibility)
    for file in files:
        native.export_file(
            name = file,
            visibility = visibility,
            mode = mode,
        )

def export_file(visibility=None, mode="reference", *args, **kwargs):
    """ Proxy for native.export file """
    return native.export_file(
        visibility = get_visibility(visibility),
        mode = mode,
        *args,
        **kwargs)
