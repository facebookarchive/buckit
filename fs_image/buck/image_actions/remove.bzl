load("//fs_image/buck:image_feature.bzl", "image_feature")

def image_remove(dest, must_exist = True):
    remove_spec = {
        "action": "assert_exists" if must_exist else "if_exists",
        "path": dest,
    }
    return image_feature(remove_paths = [remove_spec])
