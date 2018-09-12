load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")

def _convert_labels(platform, *labels):
    """
    Adds some default labels/tags to a list of labels based on the runtime configuration

    Args:
        platform: The fbcode platform in use
        *labels: Labels that should be appended to the full list

    Returns:
        A list of labels to use in a build rule
    """
    new_labels = [
        "buck",
        config.get_build_mode(),
        compiler.get_compiler_for_current_buildfile(),
        platform,
        platform_utils.get_platform_architecture(platform),
    ] + list(labels)
    sanitizer_label = sanitizers.get_label()
    if sanitizer_label:
        new_labels.append(sanitizer_label)
    return new_labels

label_utils = struct(
    convert_labels = _convert_labels,
)
