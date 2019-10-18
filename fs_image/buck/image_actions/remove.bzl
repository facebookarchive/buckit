load("//fs_image/buck:image_feature.bzl", "image_feature_INTERNAL_ONLY")

def image_remove(dest, must_exist = True):
    remove_spec = {
        "action": "assert_exists" if must_exist else "if_exists",
        "path": dest,
    }
    return image_feature_INTERNAL_ONLY(remove_paths = [remove_spec])
