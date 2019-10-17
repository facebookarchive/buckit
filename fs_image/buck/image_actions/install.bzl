load("//fs_image/buck:add_stat_options.bzl", "add_stat_options")
load("//fs_image/buck:image_feature.bzl", "image_feature")

def image_install_executable(source, dest, mode = None, user = None, group = None):
    install_spec = {
        "dest": dest,
        "source": source,
    }
    add_stat_options(install_spec, mode, user, group)
    return image_feature(install_executables = [install_spec])

def image_install_data(source, dest, mode = None, user = None, group = None):
    install_spec = {
        "dest": dest,
        "source": source,
    }
    add_stat_options(install_spec, mode, user, group)
    return image_feature(install_data = [install_spec])
