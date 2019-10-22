load("//fs_image/buck:image_feature.bzl", "image_feature_INTERNAL_ONLY")

def image_rpms_install(rpmlist):
    rpm_spec = {p: "install" for p in rpmlist}
    return image_feature_INTERNAL_ONLY(rpms = rpm_spec)

def image_rpms_remove_if_exists(rpmlist):
    rpm_spec = {p: "remove_if_exists" for p in rpmlist}
    return image_feature_INTERNAL_ONLY(rpms = rpm_spec)
