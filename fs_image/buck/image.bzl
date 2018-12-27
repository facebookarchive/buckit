"This provides a more friendly UI to the image_* macros."

load("//fs_image/buck:image_feature.bzl", "image_feature")
load("//fs_image/buck:image_layer.bzl", "image_layer")
load("//fs_image/buck:image_package.bzl", "image_package")

image = struct(
    layer = image_layer,
    feature = image_feature,
    package = image_package,
)
