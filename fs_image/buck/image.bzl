"This provides a more friendly UI to the image_* macros."

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

def _add_stat_options(d, mode, user, group):
    if mode != None:
        d["mode"] = mode
    if user != None or group != None:
        if user == None:
            user = "root"
        if group == None:
            group = "root"
        d["user_group"] = "{}:{}".format(user, group)

def image_mkdir(parent, dest, mode = None, user = None, group = None):
    dir_spec = {
        "into_dir": parent,
        "path_to_make": dest,
    }
    _add_stat_options(dir_spec, mode, user, group)
    return image_feature(make_dirs = [dir_spec])

def image_install_data(source, dest, mode = None, user = None, group = None):
    install_spec = {
        "dest": dest,
        "source": source,
    }
    _add_stat_options(install_spec, mode, user, group)
    return image_feature(install_data = [install_spec])

def image_install_executable(source, dest, mode = None, user = None, group = None):
    install_spec = {
        "dest": dest,
        "source": source,
    }
    _add_stat_options(install_spec, mode, user, group)
    return image_feature(install_executables = [install_spec])

def image_tarball(source, dest, force_root_ownership = False):
    tarball_spec = {
        "force_root_ownership": force_root_ownership,
        "into_dir": dest,
        "source": source,
    }
    return image_feature(tarballs = [tarball_spec])

def image_remove(dest, must_exist = True):
    remove_spec = {
        "action": "assert_exists" if must_exist else "if_exists",
        "path": dest,
    }
    return image_feature(remove_paths = [remove_spec])

def image_install_rpms(rpmlist):
    rpm_spec = {p: "install" for p in rpmlist}
    return image_feature(rpms = rpm_spec)

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
