load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs:allocators.bzl", "allocators")
load("@fbcode_macros//build_defs:build_info.bzl", "build_info")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_number")

def _get_rust_binary_deps(base_path, name, linker_flags, allocator):
    deps = []

    allocator = allocators.normalize_allocator(allocator)

    deps.extend(
        cpp_common.get_binary_link_deps(
            base_path,
            name,
            linker_flags,
            allocator,
        ),
    )

    # Always explicitly add libc - except for sanitizer modes, since
    # they already add them
    libc = target_utils.ThirdPartyRuleTarget("glibc", "c")
    if libc not in deps:
        deps.append(libc)

    # Always explicitly add libstdc++ - except for sanitizer modes, since
    # they already add them
    libgcc = target_utils.ThirdPartyRuleTarget("libgcc", "stdc++")
    if libgcc not in deps:
        deps.append(libgcc)
    return deps

def _convert_rust(
        name,
        fbconfig_rule_type,
        srcs = None,
        deps = None,
        rustc_flags = None,
        features = None,
        crate = None,
        link_style = None,
        preferred_linkage = None,
        visibility = None,
        external_deps = None,
        crate_root = None,
        linker_flags = None,
        framework = True,
        unittests = True,
        proc_macro = False,
        tests = None,
        test_features = None,
        test_rustc_flags = None,
        test_link_style = None,
        test_linker_flags = None,
        test_srcs = None,
        test_deps = None,
        test_external_deps = None,
        allocator = None,
        **kwargs):
    _ignore = kwargs

    dependencies = []

    visibility = get_visibility(visibility, name)

    base_path = native.package_name()

    is_binary = fbconfig_rule_type in ("rust_binary", "rust_unittest")

    is_test = fbconfig_rule_type in ("rust_unittest",)

    attributes = {}

    attributes["name"] = name
    attributes["srcs"] = src_and_dep_helpers.convert_source_list(base_path, srcs or [])
    attributes["features"] = features or []

    if not crate_root and not is_test:
        # Compute a crate_root if one wasn't specified. We'll need this
        # to pass onto the generated test rule.
        topsrc_options = ((crate or name) + ".rs",)
        if fbconfig_rule_type == "rust_binary":
            topsrc_options += ("main.rs",)
        if fbconfig_rule_type == "rust_library":
            topsrc_options += ("lib.rs",)

        topsrc = []
        for s in srcs or []:
            if s.startswith(":"):
                continue
            if paths.basename(s) in topsrc_options:
                topsrc.append(s)

        # Not sure what to do about too many or not enough crate roots
        if len(topsrc) == 1:
            crate_root = topsrc[0]

    if crate_root:
        attributes["crate_root"] = crate_root

    if rustc_flags:
        attributes["rustc_flags"] = rustc_flags

    if crate:
        attributes["crate"] = crate

    attributes["default_platform"] = platform_utils.get_buck_platform_for_base_path(base_path)

    if is_binary:
        platform = platform_utils.get_platform_for_base_path(base_path)
        if not link_style:
            link_style = cpp_common.get_link_style()

        attributes["link_style"] = link_style

        ldflags = cpp_common.get_ldflags(
            base_path,
            name,
            fbconfig_rule_type,
            binary = True,
            build_info = True,
            platform = platform,
        )
        attributes["linker_flags"] = ldflags + (linker_flags or [])

        # Add the Rust build info lib to deps.
        rust_build_info = _create_rust_build_info_rule(
            base_path,
            name,
            crate,
            fbconfig_rule_type,
            platform,
            visibility,
        )
        dependencies.append(rust_build_info)

    else:
        if proc_macro:
            attributes["proc_macro"] = proc_macro

        if preferred_linkage:
            attributes["preferred_linkage"] = preferred_linkage

    if rustc_flags:
        attributes["rustc_flags"] = rustc_flags

    if visibility:
        attributes["visibility"] = visibility

    # Translate dependencies.
    for dep in deps or []:
        dependencies.append(target_utils.parse_target(dep, default_base_path = base_path))

    # Translate external dependencies.
    for dep in external_deps or []:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

    if not tests:
        tests = []

    # Add test rule for all library/binary rules
    # It has the same set of srcs and dependencies as the base rule,
    # but also allows additional test srcs, deps and external deps.
    # test_features and test_rustc_flags override the base rule keys,
    # if present.
    if not is_test and unittests:
        test_name = _create_rust_test_rule(
            fbconfig_rule_type,
            base_path,
            dependencies,
            attributes,
            test_srcs,
            test_deps,
            test_external_deps,
            test_rustc_flags,
            test_features,
            test_link_style,
            test_linker_flags,
            allocator,
            visibility,
        )
        tests.append(":" + test_name)
        attributes["tests"] = tests

    if is_test:
        attributes["framework"] = framework

    # Add in binary-specific link deps.
    # Do this after creating the test rule, so that it doesn't pick this
    # up as well (it will add its own binary deps as needed)
    if is_binary:
        d = _get_rust_binary_deps(
            base_path,
            name,
            linker_flags,
            allocator,
        )
        dependencies.extend(d)

    # If any deps were specified, add them to the output attrs.
    if dependencies:
        attributes["deps"], attributes["platform_deps"] = (
            src_and_dep_helpers.format_all_deps(dependencies)
        )

    return attributes

def _create_rust_test_rule(
        fbconfig_rule_type,
        base_path,
        dependencies,
        attributes,
        test_srcs,
        test_deps,
        test_external_deps,
        test_rustc_flags,
        test_features,
        test_link_style,
        test_linker_flags,
        allocator,
        visibility):
    """
    Construct a rust_test rule corresponding to a rust_library or
    rust_binary rule so that internal unit tests can be run.
    """
    test_attributes = {}

    name = "%s-unittest" % attributes["name"]

    test_attributes["name"] = name
    if visibility != None:
        test_attributes["visibility"] = visibility

    # Regardless of the base rule type, the resulting unit test is always
    # an executable which needs to have buildinfo.
    ldflags = cpp_common.get_ldflags(
        base_path,
        name,
        fbconfig_rule_type,
        binary = True,
        strip_mode = None,
        build_info = True,
        platform = platform_utils.get_platform_for_base_path(base_path),
    )

    test_attributes["default_platform"] = platform_utils.get_buck_platform_for_base_path(base_path)

    if "crate" in attributes:
        test_attributes["crate"] = "%s_unittest" % attributes["crate"]

    if "crate_root" in attributes:
        test_attributes["crate_root"] = attributes["crate_root"]

    if test_rustc_flags:
        test_attributes["rustc_flags"] = test_rustc_flags
    elif "rustc_flags" in attributes:
        test_attributes["rustc_flags"] = attributes["rustc_flags"]

    if test_features:
        test_attributes["features"] = test_features
    elif "features" in attributes:
        test_attributes["features"] = attributes["features"]

    link_style = cpp_common.get_link_style()
    if test_link_style:
        link_style = test_link_style
    elif "link_style" in attributes:
        link_style = attributes["link_style"]
    test_attributes["link_style"] = link_style

    test_attributes["linker_flags"] = ldflags + (test_linker_flags or [])

    test_attributes["srcs"] = list(attributes.get("srcs", []))
    if test_srcs:
        test_attributes["srcs"] += (
            src_and_dep_helpers.convert_source_list(base_path, test_srcs)
        )

    deps = []
    deps.extend(dependencies)
    for dep in test_deps or []:
        deps.append(target_utils.parse_target(dep, default_base_path = base_path))
    for dep in test_external_deps or []:
        deps.append(src_and_dep_helpers.normalize_external_dep(dep))

    d = _get_rust_binary_deps(
        base_path,
        name,
        test_attributes["linker_flags"],
        allocator,
    )
    deps.extend(d)

    test_attributes["deps"], test_attributes["platform_deps"] = (
        src_and_dep_helpers.format_all_deps(deps)
    )

    fb_native.rust_test(**test_attributes)

    return test_attributes["name"]

def _create_rust_build_info_rule(
        base_path,
        name,
        crate,
        rule_type,
        platform,
        visibility):
    """
    Create rules to generate a Rust library with build info.
    """

    info = (
        build_info.get_build_info(
            base_path,
            name,
            rule_type,
            platform,
        )
    )

    template = """
#[derive(Debug, Copy, Clone, Eq, PartialEq, Ord, PartialOrd, Hash)]
pub struct BuildInfo {
"""

    # Construct a template
    for k, v in info.items():
        rust_type = "u64" if is_number(v) else "&'static str"
        template += "  pub %s: %s,\n" % (k, rust_type)
    template += "}\n"

    template += """
pub const BUILDINFO: BuildInfo = BuildInfo {
"""
    for k, v in info.items():
        if is_number(v):
            template += "  %s: %s,\n" % (k, v)
        else:
            template += "  %s: \"%s\",\n" % (k, v)
    template += "};\n"

    # Setup a rule to generate the build info Rust file.
    source_name = name + "-rust-build-info"
    source_attrs = {}
    source_attrs["name"] = source_name
    if visibility != None:
        source_attrs["visibility"] = visibility
    source_attrs["out"] = "lib.rs"
    source_attrs["cmd"] = (
        "mkdir -p `dirname $OUT` && echo {0} > $OUT"
            .format(shell.quote(template))
    )
    fb_native.genrule(**source_attrs)

    # Setup a rule to compile the build info C file into a library.
    lib_name = name + "-rust-build-info-lib"
    lib_attrs = {}
    lib_attrs["name"] = lib_name
    if visibility != None:
        lib_attrs["visibility"] = visibility
    lib_attrs["crate"] = (crate or name) + "_build_info"
    lib_attrs["preferred_linkage"] = "static"
    lib_attrs["srcs"] = [":" + source_name]
    lib_attrs["default_platform"] = platform_utils.get_buck_platform_for_base_path(base_path)
    fb_native.rust_library(**lib_attrs)

    return target_utils.RootRuleTarget(base_path, lib_name)

rust_common = struct(
    convert_rust = _convert_rust,
    get_rust_binary_deps = _get_rust_binary_deps,
    create_rust_test_rule = _create_rust_test_rule,
)
