load("//fs_image/buck:image_feature.bzl", "image_feature")

def image_install_rpms(rpmlist):
    rpm_spec = {p: "install" for p in rpmlist}
    return image_feature(rpms = rpm_spec)
