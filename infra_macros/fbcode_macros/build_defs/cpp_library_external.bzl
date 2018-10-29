load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@bazel_skylib//lib:types.bzl", "types")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:modules.bzl", "modules")
load("@fbcode_macros//build_defs:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

def __maybe_add_module(original_name, module_rule_name, module_name, inc_dirs, dependencies, flags, platform, local_submodule_visibility):
    # If the first include dir has a `module.modulemap` file, auto-
    # generate a module rule for it.
    if (not inc_dirs or
        not native.glob([paths.join(
            inc_dirs[0],
            "module.modulemap",
        )])):
        return None

    # Create the module compilation rule.
    modules.gen_tp2_cpp_module(
        name = module_rule_name,
        module_name = module_name,
        platform = platform,
        header_dir = inc_dirs[0],
        dependencies = dependencies,
        local_submodule_visibility = local_submodule_visibility,
        flags = flags,
        visibility = ["//{}:{}".format(native.package_name(), original_name)],
        labels = ["generated"],
    )
    return "-fmodule-file={}=$(location :{})".format(module_name, module_rule_name)

def cpp_library_external(
        name,
        link_whole = None,
        force_shared = None,
        force_static = None,
        header_only = None,
        include_dir = None,
        deps = (),
        external_deps = (),
        propagated_pp_flags = (),
        linker_flags = (),
        soname = None,
        mode = None,
        shared_only = None,  # TODO: Deprecate?
        imports = None,
        implicit_project_deps = True,
        modules_local_submodule_visibility = False,
        supports_omnibus = None,
        visibility = None,
        link_without_soname = False,
        modular_headers = True,
        static_lib = None,
        static_pic_lib = None,
        shared_lib = None,
        versioned_static_lib = None,
        versioned_static_pic_lib = None,
        versioned_shared_lib = None,
        versioned_header_dirs = None):
    """
    A cpp_library with pre-built third-party artifacts

    This can also optionally create a C++ module rule if module support is enabled

    Args:
        name: The name of the rule
        link_whole: Whether or not to tell the linker to link everything
                    (e.g. -Wl,--whole-archive)
        force_shared: Whether to only use shared libs, regardless of whether static
                      libs are provided
        force_static: Whether to only use static libs, regardless of whether shared
                      libs are provided
        header_only: See https://buckbuild.com/rule/prebuilt_cxx_library.html#header_only
        include_dir: The list of directories to use for headers. See https://buckbuild.com/rule/prebuilt_cxx_library.html#header_dirs
        deps: The list of dependencies for this rule
        external_deps: A list of strings / tuples that are used for other depending on
                       other third-party rules
        propagated_pp_flags: Extra preprocessor flags that should be re-exported to any
                             rules that depend on this one. See https://buckbuild.com/rule/prebuilt_cxx_library.html#header_only
        linker_flags: Additional linker flags to export to other rules. -Xlinker is
                      automatically prepended to any of these flags.
        soname: If provided, the name that this file should have within the C++ symlink
                tree. This can be necessary when the linker / elf information requires
                a file to have a very specific name.
        mode: Deprecated.
        shared_only: Similar to force_shared, may be deprecated in the future
        imports: Currently unused. Will be used for C++ modules
        implicit_project_deps: Whether the tp2 implicit project should be added as
                               a dependency or not
        modules_local_submodule_visibility: Whether or not to enable modules-local-submodule-visibility
                                            on module related rules that this macro
                                            generates. See `modules.gen_modules()`.
        supports_omnibus: See https://buckbuild.com/rule/prebuilt_cxx_library.html#supports_merged_linking
        visibility: The visibility of this rule. This may be modified by global settings.
        link_without_soname: Whether or not this library can be linked without an SONAME
                             property. If so, this will influence the linker
        modular_headers: Whether to build this libraries headers into a C/C++ module
                         in modular builds.
        static_lib: See https://buckbuild.com/rule/prebuilt_cxx_library.html#static_lib
        static_pic_lib: See https://buckbuild.com/rule/prebuilt_cxx_library.html#static_pic_lib
        shared_lib: See https://buckbuild.com/rule/prebuilt_cxx_library.html#shared_lib
        versioned_static_lib: See https://buckbuild.com/rule/prebuilt_cxx_library.html#versioned_static_lib
        versioned_static_pic_lib: See https://buckbuild.com/rule/prebuilt_cxx_library.html#versioned_static_pic_lib
        versioned_shared_lib: See https://buckbuild.com/rule/prebuilt_cxx_library.html#versioned_shared_lib
        versioned_header_dirs: See https://buckbuild.com/rule/prebuilt_cxx_library.html#versioned_header_dirs
    """

    # We currently have to handle `cpp_library_external` rules in fbcode,
    # until we move fboss's versioned tp2 deps to use Buck's version
    # support.

    visibility = get_visibility(visibility, name)
    build_mode = config.get_build_mode()
    base_path = native.package_name()

    platform = None
    if third_party.is_tp2(base_path):
        platform = third_party.get_tp2_platform(base_path)

    if types.is_string(include_dir):
        include_dir = [include_dir]

    dependencies = []

    # Support intra-project deps.
    for dep in deps:
        if not dep.startswith(":"):
            fail("Dependency {} must start with :".format(dep))
        dependencies.append(
            target_utils.ThirdPartyRuleTarget(os.path.dirname(base_path), dep[1:]),
        )

    if implicit_project_deps and third_party.is_tp2(base_path):
        project = third_party.get_tp2_project_name(base_path)
        dependencies.append(third_party.get_tp2_project_target(project))
    for dep in external_deps:
        dependencies.append(src_and_dep_helpers.normalize_external_dep(dep))

    lang_ppflags = {}
    versioned_lang_ppflags = []

    # If modules are enabled, automatically build a module from the module
    # map found in the first include dir, if one exists.
    if modules.enabled() and modular_headers and third_party.is_tp2(native.package_name()):
        # Add implicit toolchain module deps.
        dependencies.extend([
            target_utils.parse_target(dep)
            for dep in modules.get_implicit_module_deps()
        ])

        # Set a default module name.
        module_name = (
            modules.get_module_name(
                "third-party",
                third_party.get_tp2_project_name(base_path),
                name,
            )
        )

        # Add implicit module rule for the main header dir.
        module_flags = __maybe_add_module(name, name + "-module", module_name, include_dir, dependencies, propagated_pp_flags, platform, modules_local_submodule_visibility)
        if module_flags:
            lang_ppflags.setdefault("cxx", []).append(module_flags)

        # Add implicit module rules for versioned header dirs.
        for idx, (constraints, inc_dirs) in enumerate(versioned_header_dirs or ()):
            versioned_lang_ppflags.append((constraints, {}))
            module_flags = __maybe_add_module(name, name + "-module-v" + str(idx), module_name, inc_dirs, dependencies, propagated_pp_flags, platform, modules_local_submodule_visibility)
            if module_flags:
                versioned_lang_ppflags[-1][1].setdefault("cxx", []).append(module_flags)

    should_not_have_libs = header_only or (mode != None and not mode)
    if force_shared or shared_only or should_not_have_libs:
        static_lib = None
        static_pic_lib = None
        versioned_static_lib = None
        versioned_static_pic_lib = None
    if force_static or should_not_have_libs:
        shared_lib = None
        versioned_shared_lib = None

    # Set preferred linkage.
    preferred_linkage = None
    if force_shared or shared_only:
        preferred_linkage = "shared"
    elif force_static:
        preferred_linkage = "static"

    exported_linker_flags = []
    for flag in linker_flags:
        exported_linker_flags.append("-Xlinker")
        exported_linker_flags.append(flag)

    # TODO(#8334786): There's some strange hangs when linking third-party
    # `--as-needed`.  Enable when these are debugged.
    if build_mode.startswith("dev"):
        exported_linker_flags.append("-Wl,--no-as-needed")

    exported_deps = None
    if dependencies:
        exported_deps = src_and_dep_helpers.format_deps(dependencies, platform = platform)

    fb_native.prebuilt_cxx_library(
        name = name,
        visibility = visibility,
        # We're header only if explicitly set, or if `mode` is set to an empty list.,
        header_only = (header_only or (mode != None and not mode)),
        link_whole = link_whole,
        exported_linker_flags = exported_linker_flags,
        exported_preprocessor_flags = propagated_pp_flags,
        exported_lang_preprocessor_flags = lang_ppflags,
        versioned_exported_lang_preprocessor_flags = versioned_lang_ppflags,
        exported_deps = exported_deps,
        supports_merged_linking = supports_omnibus,
        provided = force_shared,
        preferred_linkage = preferred_linkage,
        static_lib = static_lib,
        static_pic_lib = static_pic_lib,
        shared_lib = shared_lib,
        header_dirs = include_dir,
        versioned_static_lib = versioned_static_lib,
        versioned_static_pic_lib = versioned_static_pic_lib,
        versioned_shared_lib = versioned_shared_lib,
        versioned_header_dirs = versioned_header_dirs,
        soname = soname,
        link_without_soname = link_without_soname,
    )
