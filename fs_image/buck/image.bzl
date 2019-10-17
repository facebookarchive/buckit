"This provides a more friendly UI to the image_* macros."

load("//fs_image/buck/image_actions:install.bzl", "image_install_data", "image_install_executable")
load("//fs_image/buck/image_actions:mkdir.bzl", "image_mkdir")
load("//fs_image/buck/image_actions:remove.bzl", "image_remove")
load("//fs_image/buck/image_actions:rpms.bzl", "image_install_rpms")
load("//fs_image/buck/image_actions:tarball.bzl", "image_tarball")
load(":image_cpp_unittest.bzl", "image_cpp_unittest")
load(":image_feature.bzl", "image_feature")
load(
    ":image_layer.bzl",
    "image_layer",
    "image_rpmbuild_layer",
    "image_sendstream_layer",
)
load(":image_layer_alias.bzl", "image_layer_alias")
load(":image_package.bzl", "image_package")
load(":image_python_unittest.bzl", "image_python_unittest")
load(":image_source.bzl", "image_source")

def _image_host_mount(source, mountpoint, is_directory):
    return {
        "mount_config": {
            "build_source": {"source": source, "type": "host"},
            # For `host` mounts, `runtime_source` is required to be empty.
            "default_mountpoint": source if mountpoint == None else mountpoint,
            "is_directory": is_directory,
        },
    }

def image_layer_mount(source, mountpoint = None):
    if mountpoint == None:
        mount_spec = [source]
    else:
        mount_spec = [(mountpoint, source)]
    return image_feature(mounts = mount_spec)

def image_host_dir_mount(source, mountpoint = None):
    return image_feature(mounts = [_image_host_mount(
        source,
        mountpoint,
        is_directory = True,
    )])

def image_host_file_mount(source, mountpoint = None):
    return image_feature(mounts = [_image_host_mount(
        source,
        mountpoint,
        is_directory = False,
    )])

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

def image_uninstall_rpms(rpmlist):
    rpm_spec = {p: "remove_if_exists" for p in rpmlist}
    return image_feature(rpms = rpm_spec)

def image_symlink_dir(link_target, link_name):
    return image_feature(symlinks_to_dirs = {link_target: link_name})

def image_symlink_file(link_target, link_name):
    return image_feature(symlinks_to_files = {link_target: link_name})

image = struct(
    cpp_unittest = image_cpp_unittest,
    feature = image_named_feature,
    mkdir = image_mkdir,
    install_data = image_install_data,
    install_executable = image_install_executable,
    tarball = image_tarball,
    remove = image_remove,
    install_rpms = image_install_rpms,
    uninstall_rpms = image_uninstall_rpms,
    symlink_dir = image_symlink_dir,
    symlink_file = image_symlink_file,
    host_dir_mount = image_host_dir_mount,
    host_file_mount = image_host_file_mount,
    layer_mount = image_layer_mount,
    layer = image_layer,
    layer_alias = image_layer_alias,
    opts = struct,
    package = image_package,
    python_unittest = image_python_unittest,
    rpmbuild_layer = image_rpmbuild_layer,
    sendstream_layer = image_sendstream_layer,
    source = image_source,
)
