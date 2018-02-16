"""
Quick function that re-exports files
"""

def export_files(files, visibility=None):
    """ Takes a list of files, and exports each of them """
    if visibility == None:
        visibility = ["PUBLIC"]
    for file in files:
        native.export_file(
            name = file,
            visibility = visibility,
        )

def export_file(*args, **kwargs):
    """ Proxy for native.export file """
    return native.export_file(*args, **kwargs)
