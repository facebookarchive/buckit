load("@fbcode_macros//build_defs/lib:lua_common.bzl", "lua_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_dict")

def _convert_sources(base_path, srcs):
    if is_dict(srcs):
        return src_and_dep_helpers.convert_source_map(
            base_path,
            {v: k for k, v in srcs.items()},
        )
    else:
        return src_and_dep_helpers.convert_source_list(base_path, srcs)

def lua_library(
        name,
        base_module = None,
        srcs = (),
        deps = (),
        external_deps = (),
        visibility = None):
    """
    Buckify a library rule.
    """
    base_path = native.package_name()
    dependencies = []
    if third_party.is_tp2(base_path):
        dependencies.append(
            third_party.get_tp2_project_target(
                third_party.get_tp2_project_name(base_path),
            ),
        )
    for dep in deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))
    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))
    attributes = {}
    if dependencies:
        platform = (
            third_party.get_tp2_platform(base_path) if third_party.is_tp2(base_path) else None
        )
        attributes["deps"], attributes["platform_deps"] = (
            src_and_dep_helpers.format_all_deps(dependencies, platform = platform)
        )

    fb_native.lua_library(
        name = name,
        visibility = get_visibility(visibility, name),
        srcs = _convert_sources(base_path, srcs),
        base_module = lua_common.get_lua_base_module(
            base_path,
            base_module = base_module,
        ),
        **attributes
    )
