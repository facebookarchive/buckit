load("@fbcode_macros//build_defs/lib:modules.bzl", "modules")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def cpp_module_external(
        name,
        module_name = None,
        include_dir = "include",
        external_deps = (),
        propagated_pp_flags = None,
        modules_local_submodule_visibility = False,
        implicit_project_dep = True,
        visibility = None):
    base_path = native.package_name()
    propagated_pp_flags = propagated_pp_flags or []

    # Set a default module name.
    if module_name == None:
        module_name = (
            modules.get_module_name(
                "third-party",
                third_party.get_tp2_project_name(base_path),
                name,
            )
        )

    # Setup dependencies.
    dependencies = []
    if implicit_project_dep:
        project = base_path.split("/")[3]
        dependencies.append(third_party.get_tp2_project_target(project))
    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

    platform = third_party.get_tp2_platform(base_path)

    # Generate the module file.
    module_rule_name = name + "-module"
    modules.gen_tp2_cpp_module(
        name = module_rule_name,
        module_name = module_name,
        header_dir = include_dir,
        local_submodule_visibility = modules_local_submodule_visibility,
        flags = propagated_pp_flags,
        dependencies = dependencies,
        visibility = ["//{}:{}".format(base_path, name)],
        platform = platform,
    )

    # Wrap with a `cxx_library`, propagating the module map file via the
    # `-fmodule-file=...` flag in it's exported preprocessor flags so that
    # dependents can easily access the module.
    out_exported_preprocessor_flags = []
    out_exported_preprocessor_flags.extend(propagated_pp_flags)
    out_exported_preprocessor_flags.append(
        "-fmodule-file={}=$(location :{})"
            .format(module_name, module_rule_name),
    )

    # Setup platform default for compilation DB, and direct building.
    buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)

    fb_native.cxx_library(
        name = name,
        exported_lang_preprocessor_flags = (
            {"cxx": out_exported_preprocessor_flags}
        ),
        exported_deps = (
            src_and_dep_helpers.format_deps(
                dependencies,
                fbcode_platform = platform,
            )
        ),
        visibility = get_visibility(visibility, name),
        default_platform = buck_platform,
        defaults = {"platform": buck_platform},
    )

    return []
