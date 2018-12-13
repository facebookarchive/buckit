load("@fbcode_macros//build_defs/lib:haskell_rules.bzl", "haskell_rules")
load("@fbcode_macros//build_defs/lib:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def haskell_unittest(
        name,
        main = None,
        tags = (),
        env = None,
        srcs = (),
        deps = (),
        external_deps = (),
        packages = (),
        compiler_flags = (),
        warnings_flags = (),
        lang_opts = (),
        enable_haddock = False,
        haddock_flags = None,
        enable_profiling = None,
        ghci_bin_dep = None,
        ghci_init = None,
        extra_script_templates = (),
        eventlog = None,
        link_whole = None,
        force_static = None,
        fb_haskell = True,
        allocator = "jemalloc",
        dlls = {},
        visibility = None):
    base_path = native.package_name()

    # Generate the test binary rule and fixup the name.
    binary_name = name + "-binary"
    fb_native.haskell_binary(
        **haskell_rules.convert_rule(
            rule_type = "haskell_unittest",
            base_path = base_path,
            name = binary_name,
            main = main,
            srcs = srcs,
            deps = deps,
            external_deps = external_deps,
            packages = packages,
            compiler_flags = compiler_flags,
            warnings_flags = warnings_flags,
            lang_opts = lang_opts,
            enable_haddock = enable_haddock,
            haddock_flags = haddock_flags,
            enable_profiling = enable_profiling,
            ghci_bin_dep = ghci_bin_dep,
            ghci_init = ghci_init,
            extra_script_templates = extra_script_templates,
            eventlog = eventlog,
            link_whole = link_whole,
            force_static = force_static,
            fb_haskell = fb_haskell,
            allocator = allocator,
            dlls = dlls,
            visibility = visibility,
        )
    )

    platform = platform_utils.get_platform_for_base_path(base_path)

    # Create a `sh_test` rule to wrap the test binary and set it's tags so
    # that testpilot knows it's a haskell test.
    fb_native.sh_test(
        name = name,
        visibility = get_visibility(visibility, name),
        test = ":" + binary_name,
        env = env,
        labels = (
            label_utils.convert_labels(platform, "haskell", "custom-type-hs", *tags)
        ),
    )
