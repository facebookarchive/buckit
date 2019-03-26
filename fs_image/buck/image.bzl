"This provides a more friendly UI to the image_* macros."

load(":image_feature.bzl", "image_feature")
load(":image_layer.bzl", "image_layer")
load(":image_package.bzl", "image_package")

def _image_host_mount(source, mountpoint, is_directory):
    return {
        "mount_config": {
            "build_source": {"source": source, "type": "host"},
            # For `host` mounts, `runtime_source` is required to be empty.
            "default_mountpoint": source if mountpoint == None else mountpoint,
            "is_directory": is_directory,
        },
    }

def image_host_dir_mount(source, mountpoint = None):
    return _image_host_mount(source, mountpoint, is_directory = True)

def image_host_file_mount(source, mountpoint = None):
    return _image_host_mount(source, mountpoint, is_directory = False)

image = struct(
    layer = image_layer,
    feature = image_feature,
    host_dir_mount = image_host_dir_mount,
    host_file_mount = image_host_file_mount,
    package = image_package,
)
