load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:string_macros.bzl", "string_macros")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")

# save original native module before it's shadowed by the attribute
_native = native

def _convert_ocaml(
        name,
        rule_type,
        srcs = (),
        deps = (),
        compiler_flags = None,
        ocamldep_flags = None,
        native = True,
        warnings_flags = None,
        supports_coverage = None,
        external_deps = (),
        visibility = None,
        ppx_flag = None,
        nodefaultlibs = False):
    _ignore = supports_coverage
    base_path = _native.package_name()
    is_binary = rule_type == "ocaml_binary"

    # Translate visibility
    visibility = get_visibility(visibility, name)
    platform = platform_utils.get_platform_for_base_path(base_path)

    attributes = {}

    attributes["name"] = name

    attributes["srcs"] = src_and_dep_helpers.convert_source_list(base_path, srcs)

    attributes["visibility"] = visibility

    if warnings_flags:
        attributes["warnings_flags"] = warnings_flags

    attributes["compiler_flags"] = ["-warn-error", "+a", "-safe-string"]
    if compiler_flags:
        attributes["compiler_flags"].extend(
            string_macros.convert_args_with_macros(
                compiler_flags,
                platform = platform,
            ),
        )

    attributes["ocamldep_flags"] = []
    if ocamldep_flags:
        attributes["ocamldep_flags"].extend(ocamldep_flags)

    if ppx_flag != None:
        attributes["compiler_flags"].extend(["-ppx", ppx_flag])
        attributes["ocamldep_flags"].extend(["-ppx", ppx_flag])

    if not native:
        attributes["bytecode_only"] = True

    if rule_type == "ocaml_binary":
        attributes["platform"] = platform_utils.get_buck_platform_for_base_path(base_path)

    dependencies = []

    # Add the C/C++ build info lib to deps.
    if rule_type == "ocaml_binary":
        cxx_build_info = cpp_common.cxx_build_info_rule(
            base_path,
            name,
            rule_type,
            platform,
            visibility = visibility,
        )
        dependencies.append(cxx_build_info)

    # Translate dependencies.
    for dep in deps:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))

    # Translate external dependencies.
    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

    # Add in binary-specific link deps.
    if is_binary:
        dependencies.extend(
            cpp_common.get_binary_link_deps(
                base_path,
                name,
                default_deps = not nodefaultlibs,
            ),
        )

    # If any deps were specified, add them to the output attrs.
    if dependencies:
        attributes["deps"], attributes["platform_deps"] = (
            src_and_dep_helpers.format_all_deps(dependencies)
        )

    platform = platform_utils.get_platform_for_base_path(base_path)

    ldflags = cpp_common.get_ldflags(
        base_path,
        name,
        rule_type,
        binary = is_binary,
        platform = platform if is_binary else None,
    )

    if nodefaultlibs:
        ldflags.append("-nodefaultlibs")

    if "-flto" in ldflags:
        attributes["compiler_flags"].extend(["-ccopt", "-flto", "-cclib", "-flto"])
    if "-flto=thin" in ldflags:
        attributes["compiler_flags"].extend(["-ccopt", "-flto=thin", "-cclib", "-flto=thin"])

    return attributes

ocaml_common = struct(
    convert_ocaml = _convert_ocaml,
)
