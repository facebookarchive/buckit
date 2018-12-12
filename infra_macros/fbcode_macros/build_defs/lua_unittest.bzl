load("@fbcode_macros//build_defs/lib:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:lua_binary.bzl", "lua_binary")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def lua_unittest(
        name,
        tags = (),
        type = "lua",
        visibility = None,
        **kwargs):
    """
    Buckify a unittest rule.
    """
    base_path = native.package_name()

    # Generate the test binary rule and fixup the name.
    binary_name = name + "-binary"
    lua_binary(
        name = name,
        binary_name = binary_name,
        package_style = "inplace",
        visibility = visibility,
        is_test = True,
        **kwargs
    )

    # Create a `sh_test` rule to wrap the test binary and set it's tags so
    # that testpilot knows it's a lua test.
    platform = platform_utils.get_platform_for_base_path(base_path)
    fb_native.sh_test(
        name = name,
        visibility = get_visibility(visibility, name),
        test = ":" + binary_name,
        labels = (
            label_utils.convert_labels(platform, "lua", "custom-type-" + type, *tags)
        ),
    )
