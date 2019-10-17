load("//fs_image/buck:image_feature.bzl", "image_feature")
load("//fs_image/buck:maybe_export_file.bzl", "maybe_export_file")

def image_tarball(source, dest, force_root_ownership = False):
    tarball_spec = {
        "force_root_ownership": force_root_ownership,
        "into_dir": dest,
        "source": maybe_export_file(source),
    }
    return image_feature(tarballs = [tarball_spec])
