load("//fs_image/buck:image_feature.bzl", "image_feature")

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

def image_layer_mount(source, mountpoint = None):
    if mountpoint == None:
        mount_spec = [source]
    else:
        mount_spec = [(mountpoint, source)]
    return image_feature(mounts = mount_spec)
