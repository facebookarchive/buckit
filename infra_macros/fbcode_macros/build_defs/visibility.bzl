"""
Functions that handle correcting 'visiblity' arguments
"""

def get_visibility(visibility_attr):
    """
    Returns either the provided visibility list, or a default visibility if None
    """
    if visibility_attr == None:
        return ["PUBLIC"]
    else:
        return visibility_attr
