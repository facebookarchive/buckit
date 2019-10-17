load("//fs_image/buck:image_feature.bzl", "image_feature")

def image_named_feature(name = None, features = None, visibility = None):
    """This is the main image.feature() interface.

    It doesn't define any actions itself (there are more specific rules for the
    actions), but image.feature() serves three purposes:

    1) To group multiple features, using the features = [...] argument.

    2) To give the features a name, so they can be referred to using a
       ":buck_target" notation.

    3) To specify a custom visibility for a set of features.

    For features that execute actions that are used to build the container
    (install RPMs, remove files/directories, create symlinks or directories,
    copy executable or data files, declare mounts), see the more specific
    features meant for a specific purpose.
    """
    return image_feature(name = name, features = features, visibility = visibility)
