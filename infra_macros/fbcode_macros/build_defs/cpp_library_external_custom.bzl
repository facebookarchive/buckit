load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:third_party.bzl", "third_party")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbsource//tools/build_defs:type_defs.bzl", "is_list", "is_tuple")

def _first(*args):
    for arg in args:
        if arg != None:
            return arg
    return None

def _is_collection(obj):
    """
    Return whether the object is a array-like collection.
    """

    return is_list(obj) or is_tuple(obj)

def _translate_ref(lib, libs, shared = False):
    if shared:
        return "lib{}.so".format(lib)
    else:
        return str(libs.index(lib))

def _extract_lib(arg):
    """Extracts library name from name-only library reference."""
    prefix = "{LIB_"
    if not arg.startswith(prefix) or not arg.endswith("}"):
        return None
    return arg[len(prefix):-1]

def _extract_rel_lib(arg):
    """Extracts library name from full path library reference."""
    prefix = "-l{lib_"
    if not arg.startswith(prefix) or not arg.endswith("}"):
        return None
    return arg[len(prefix):-1]

def translate_link(args, libs, shared = False):
    """
    Translate the given link args into their buck equivalents.
    """

    out = []

    # Iterate over args, translating them to their buck equivalents.
    i = 0
    for _ in range(len(args)):
        if i >= len(args):
            break

        # Translate `{LIB_<name>}` references to buck-style macros.
        lib = _extract_lib(args[i])
        if lib != None:
            out.append(
                "$(lib {})".format(
                    _translate_ref(lib, libs, shared),
                ),
            )
            i += 1
            continue

        # Translate `-L{dir} -l{lib_<name>}` references to buck-style
        # macros.
        if shared and args[i] == "-L{dir}" and i < len(args) - 1:
            lib = _extract_rel_lib(args[i + 1])
            if lib != None:
                out.append(
                    "$(rel-lib {})".format(
                        _translate_ref(lib, libs, shared),
                    ),
                )
                i += 2
                continue

        # Handle the "all libs" placeholder.
        if args[i] == "{LIBS}":
            for lib in libs:
                out.append(
                    "$(lib {})".format(
                        _translate_ref(lib, libs, shared),
                    ),
                )
            i += 1
            continue

        # Otherwise, pass the argument straight to the linker.
        out.append("-Xlinker")
        out.append(args[i])
        i += 1

    return out

def cpp_library_external_custom(
        name,
        lib_dir = "lib",
        include_dir = ["include"],
        static_link = None,
        static_libs = None,
        static_pic_link = None,
        static_pic_libs = None,
        shared_link = None,
        shared_libs = None,
        propagated_pp_flags = (),
        external_deps = (),
        visibility = None):
    base_path = native.package_name()

    platform = third_party.get_tp2_platform(base_path)

    attributes = {}

    out_static_link = (
        None if static_link == None else translate_link(static_link, static_libs)
    )
    out_static_libs = (
        None if static_libs == None else [
            paths.join(lib_dir, "lib{}.a".format(s))
            for s in static_libs
        ]
    )

    out_static_pic_link = (
        None if static_pic_link == None else translate_link(static_pic_link, static_pic_libs)
    )
    out_static_pic_libs = (
        None if static_pic_libs == None else [
            paths.join(lib_dir, "lib{}.a".format(s))
            for s in static_pic_libs
        ]
    )

    out_shared_link = (
        None if shared_link == None else translate_link(shared_link, shared_libs, shared = True)
    )
    out_shared_libs = (
        None if shared_libs == None else {
            "lib{}.so".format(s): paths.join(lib_dir, "lib{}.so".format(s))
            for s in shared_libs
        }
    )

    out_include_dirs = []
    if _is_collection(include_dir):
        out_include_dirs.extend(include_dir)
    else:
        out_include_dirs.append(include_dir)
    if out_include_dirs:
        attributes["include_dirs"] = out_include_dirs

    if propagated_pp_flags:
        attributes["exported_preprocessor_flags"] = propagated_pp_flags

    dependencies = []
    for target in external_deps:
        edep = src_and_dep_helpers.normalize_external_dep(target)
        dependencies.append(
            target_utils.target_to_label(edep, platform = platform),
        )
    if dependencies:
        attributes["exported_deps"] = dependencies

    fb_native.prebuilt_cxx_library_group(
        name = name,
        visibility = get_visibility(visibility, name),
        static_link = _first(out_static_link, out_static_pic_link),
        static_libs = _first(out_static_libs, out_static_pic_libs),
        static_pic_link = (
            _first(out_static_pic_link, out_static_link)
        ),
        static_pic_libs = (
            _first(out_static_pic_libs, out_static_libs)
        ),
        shared_link = out_shared_link,
        shared_libs = out_shared_libs,
        **attributes
    )
