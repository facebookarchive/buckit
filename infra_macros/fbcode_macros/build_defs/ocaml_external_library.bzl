load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")

_native = native

def ocaml_external_library(
        name,
        include_dirs = None,
        native_libs = None,
        bytecode_libs = None,
        c_libs = None,
        native_c_libs = None,
        bytecode_c_libs = None,
        deps = (),
        external_deps = (),
        native = True,
        visibility = None):
    visibility = get_visibility(visibility, name)
    package_name = _native.package_name()
    platform = third_party.get_tp2_platform(package_name)

    include_dir = None
    if include_dirs:
        if len(include_dirs) != 1:
            fail("include_dirs may only have one element")
        include_dir = include_dirs[0]

    native_lib = None
    if native_libs:
        if len(native_libs) != 1:
            fail("native_libs may only have one element")
        native_lib = native_libs[0]

    bytecode_lib = None
    if bytecode_libs:
        if len(bytecode_libs) != 1:
            fail("bytecode_libs may only have one element")
        bytecode_lib = bytecode_libs[0]

    dependencies = [
        src_and_dep_helpers.convert_build_target(package_name, target)
        for target in deps
    ]

    for target in external_deps:
        dependencies.append(src_and_dep_helpers.convert_external_build_target(target, fbcode_platform = platform))

    # Add the implicit dep to our own project rule.
    dependencies.append(
        target_utils.target_to_label(
            third_party.get_tp2_project_target(
                third_party.get_tp2_project_name(package_name),
            ),
            fbcode_platform = platform,
        ),
    )

    _native.prebuilt_ocaml_library(
        name = name,
        visibility = visibility,
        lib_name = name,
        lib_dir = "",
        include_dir = include_dir,
        native_lib = native_lib,
        bytecode_lib = bytecode_lib,
        c_libs = c_libs,
        native_c_libs = native_c_libs,
        bytecode_c_libs = bytecode_c_libs,
        bytecode_only = not native,
        deps = dependencies,
    )
