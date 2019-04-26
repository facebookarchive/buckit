"This provides a more friendly UI to the image_* macros."

load(":image_feature.bzl", "image_feature")
load(":image_layer.bzl", "image_layer")
load(":image_package.bzl", "image_package")
load(":image_python_unittest.bzl", "image_python_unittest")

def _image_host_mount(source, mountpoint, is_directory, is_repo_root):
    return {
        "mount_config": {
            "build_source": {"source": source, "type": "host"},
            # For `host` mounts, `runtime_source` is required to be empty.
            "default_mountpoint": source if mountpoint == None else mountpoint,
            "is_directory": is_directory,
            "is_repo_root": is_repo_root,
        },
    }

def image_host_dir_mount(source = None, mountpoint = None):
    return _image_host_mount(
        source,
        mountpoint,
        is_directory = True,
        is_repo_root = False,
    )

def image_host_dir_mount_repo_root():
    return _image_host_mount(
        source = None,
        mountpoint = None,
        is_directory = True,
        is_repo_root = True,
    )

def image_host_file_mount(source, mountpoint = None):
    return _image_host_mount(
        source,
        mountpoint,
        is_directory = False,
        is_repo_root = False,
    )

image = struct(
    layer = image_layer,
    feature = image_feature,
    host_dir_mount = image_host_dir_mount,
    host_dir_mount_repo_root = image_host_dir_mount_repo_root,
    host_file_mount = image_host_file_mount,
    package = image_package,
    python_unittest = image_python_unittest,
)
