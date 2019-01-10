load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def add_gk_binary_rule(
        name,
        deps):
    """Utility to add rules to generate GK files and update deps"""

    # Wrap deps in quotes so the macro parser can handle special cases
    all_deps_filtered = ['"{0}"'.format(dep) for dep in deps]
    all_deps_macro = " ".join(all_deps_filtered)

    gk_list = name + "-gk-list"
    fb_native.genrule(
        name = gk_list,
        out = "all_gatekeepers.txt",
        cmd = ("echo $(query_outputs 'attrfilter(deps, {0}, set({1}))')" +
               " | xargs -I{{}} unzip -p {{}} {2} | sort | uniq > $OUT").format(
            "//fbplatform/gatekeeper/annotation:annotation",
            all_deps_macro,
            "META-INF/gatekeepers.txt",
        ),
    )

    gk_definition_gen = name + "-gk-definition-gen"
    fb_native.genrule(
        name = gk_definition_gen,
        out = "GKRoot.java",
        cmd = "$(exe {0}) $(location //{1}:{2}) > $OUT"
            .format(
            "//fbplatform/gatekeeper/codegen:generator",
            native.package_name(),
            gk_list,
        ),
    )

    gk_definition_lib = name + "-gk-definition-lib"
    fb_native.java_library(
        name = gk_definition_lib,
        srcs = [
            ":" + gk_definition_gen,
        ],
    )
    deps.append(":" + gk_definition_lib)
