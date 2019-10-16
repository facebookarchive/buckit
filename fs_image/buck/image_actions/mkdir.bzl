load("//fs_image/buck:add_stat_options.bzl", "add_stat_options")
load("//fs_image/buck:image_feature.bzl", "image_feature")

def image_mkdir(parent, dest, mode = None, user = None, group = None):
    dir_spec = {
        "into_dir": parent,
        "path_to_make": dest,
    }
    add_stat_options(dir_spec, mode, user, group)
    return image_feature(make_dirs = [dir_spec])
