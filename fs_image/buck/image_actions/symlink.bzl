load("//fs_image/buck:image_feature.bzl", "image_feature_INTERNAL_ONLY")

def image_symlink_dir(link_target, link_name):
    symlink_spec = {
        "dest": link_name,
        "source": link_target,
    }
    return image_feature_INTERNAL_ONLY(symlinks_to_dirs = [symlink_spec])

def image_symlink_file(link_target, link_name):
    symlink_spec = {
        "dest": link_name,
        "source": link_target,
    }
    return image_feature_INTERNAL_ONLY(symlinks_to_files = [symlink_spec])
