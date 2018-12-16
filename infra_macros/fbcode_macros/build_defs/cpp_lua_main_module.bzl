load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_EMBED_DEPS_DEPENDENCIES = [
    target_utils.RootRuleTarget("tools/make_lar", "lua_main_decl"),
    target_utils.ThirdPartyRuleTarget("LuaJIT", "luajit"),
    target_utils.RootRuleTarget("common/embed", "lua"),
    target_utils.RootRuleTarget("common/embed", "python"),
]

_NO_EMBED_DEPS_DEPENDENCIES = [
    target_utils.RootRuleTarget("tools/make_lar", "lua_main_decl"),
    target_utils.ThirdPartyRuleTarget("LuaJIT", "luajit"),
]

_LUA_SPECIFIC_LINKER_FLAGS = [
    "-Dmain=lua_main",
    "-includetools/make_lar/lua_main_decl.h",
]

def cpp_lua_main_module(
        name,
        arch_compiler_flags = None,  # {}
        arch_preprocessor_flags = None,  # {}
        auto_headers = None,
        compiler_flags = (),
        compiler_specific_flags = None,  # {}
        deps = (),
        external_deps = (),
        global_symbols = (),
        header_namespace = None,
        headers = None,
        known_warnings = (),  # True or list
        lex_args = (),
        linker_flags = (),
        modules = None,
        nodefaultlibs = False,
        nvcc_flags = (),
        precompiled_header = None,
        preprocessor_flags = (),
        shared_system_deps = None,
        srcs = (),
        supports_coverage = None,
        system_include_paths = None,
        visibility = None,
        yacc_args = (),
        additional_coverage_targets = (),
        autodeps_keep = None,  # Ignore; used only by autodeps tooling.
        tags = (),
        embed_deps = True):
    # Lua main module rules depend on are custom lua main.
    #
    # When `embed_deps` is set, auto-dep deps on to the embed restore
    # libraries, which will automatically restore special env vars used
    # for loading the binary.
    rule_specific_deps = _EMBED_DEPS_DEPENDENCIES if embed_deps else _NO_EMBED_DEPS_DEPENDENCIES

    attrs = cpp_common.convert_cpp(
        name = name,
        cpp_rule_type = "cpp_lua_main_module",
        buck_rule_type = "cxx_library",
        is_library = False,
        is_buck_binary = False,
        is_test = False,
        is_deployable = False,
        rule_specific_preprocessor_flags = _LUA_SPECIFIC_LINKER_FLAGS,
        rule_specific_deps = rule_specific_deps,
        arch_compiler_flags = arch_compiler_flags or {},
        arch_preprocessor_flags = arch_preprocessor_flags or {},
        auto_headers = auto_headers,
        compiler_flags = compiler_flags,
        compiler_specific_flags = compiler_specific_flags or {},
        deps = deps,
        external_deps = external_deps,
        global_symbols = global_symbols,
        header_namespace = header_namespace,
        headers = headers,
        known_warnings = known_warnings,  # True or list
        lex_args = lex_args,
        linker_flags = linker_flags,
        modules = modules,
        nodefaultlibs = nodefaultlibs,
        nvcc_flags = nvcc_flags,
        precompiled_header = precompiled_header,
        preprocessor_flags = preprocessor_flags,
        shared_system_deps = shared_system_deps,
        srcs = srcs,
        supports_coverage = supports_coverage,
        system_include_paths = system_include_paths,
        visibility = visibility,
        yacc_args = yacc_args,
        additional_coverage_targets = additional_coverage_targets,
        autodeps_keep = autodeps_keep,  # Ignore; used only by autodeps tooling.
        tags = tags,
    )
    fb_native.cxx_library(**attrs)
