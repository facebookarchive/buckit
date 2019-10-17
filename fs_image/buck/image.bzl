"This provides a more friendly UI to the image_* macros."

load("//fs_image/buck/image_actions:install.bzl", "image_install_data", "image_install_executable")
load("//fs_image/buck/image_actions:mkdir.bzl", "image_mkdir")
load("//fs_image/buck/image_actions:mount.bzl", "image_host_dir_mount", "image_host_file_mount", "image_layer_mount")
load("//fs_image/buck/image_actions:named_feature.bzl", "image_named_feature")
load("//fs_image/buck/image_actions:remove.bzl", "image_remove")
load("//fs_image/buck/image_actions:rpms.bzl", "image_install_rpms", "image_uninstall_rpms")
load("//fs_image/buck/image_actions:symlink.bzl", "image_symlink_dir", "image_symlink_file")
load("//fs_image/buck/image_actions:tarball.bzl", "image_tarball")
load(":image_cpp_unittest.bzl", "image_cpp_unittest")
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
