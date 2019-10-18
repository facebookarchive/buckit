load("//fs_image/buck:add_stat_options.bzl", "add_stat_options")
load("//fs_image/buck:image_feature.bzl", "image_feature_INTERNAL_ONLY")
load("//fs_image/buck:maybe_export_file.bzl", "maybe_export_file")

def image_install_executable(source, dest, mode = None, user = None, group = None):
    install_spec = {
        "dest": dest,
        "source": maybe_export_file(source),
    }
    add_stat_options(install_spec, mode, user, group)
    return image_feature_INTERNAL_ONLY(install_executables = [install_spec])

def image_install_data(source, dest, mode = None, user = None, group = None):
    install_spec = {
        "dest": dest,
        "source": maybe_export_file(source),
    }
    add_stat_options(install_spec, mode, user, group)
    return image_feature_INTERNAL_ONLY(install_data = [install_spec])
