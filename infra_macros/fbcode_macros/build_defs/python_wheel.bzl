load("@bazel_skylib//lib:collections.bzl", "collections")
load("@bazel_skylib//lib:paths.bzl", "paths")
load(
    "@fbcode_macros//build_defs/lib:python_typing.bzl",
    "gen_typing_config",
    "get_typing_config_target",
)
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def _get_url_basename(url):
    """ Urls will have an #md5 etag remove it and return the wheel name"""
    return paths.basename(url).rsplit("#md5=")[0]

def _is_compiled(url):
    """
    Returns True if wheel with provided url is precompiled.

    The logic in this method is a less efficient version of
    -cp[0-9]{2}- regex matching.
    """
    prefix = "-cp"
    start = 0
    for _ in range(len(url)):
        start = url.find(prefix, start)
        if start == -1 or start + 6 >= len(url):
            break
        if url[start + len(prefix)].isdigit() and \
           url[start + len(prefix) + 1].isdigit() and \
           url[start + len(prefix) + 2] == "-":
            return True
        start += len(prefix)
    return False

def _remote_wheel(url, out, sha1, visibility):
    remote_file_name = out + "-remote"
    fb_native.remote_file(
        name = remote_file_name,
        visibility = get_visibility(visibility, remote_file_name),
        out = out,
        url = url,
        sha1 = sha1,
    )
    return ":" + remote_file_name

def _prebuilt_target(wheel, remote_target, visibility):
    fb_native.prebuilt_python_library(
        name = wheel,
        visibility = get_visibility(visibility, wheel),
        binary_src = remote_target,
    )
    return ":" + wheel

def _override_wheels(deps, wheel_platform):
    # For all deps, override the current wheel file with the one corresponding
    # to the specified wheel platform.

    # We're doing this because platforms in the list of deps are also re.escaped.
    wheel_platform = platform_utils.escape(wheel_platform)

    override_urls = None
    for platform, urls in deps:
        if wheel_platform in platform:
            override_urls = urls

    if not override_urls:
        return deps

    new_deps = []
    for platform, _ in deps:
        new_deps.append((platform, override_urls))

    return new_deps

def python_wheel(
        version,
        platform_urls,  # Dict[str, str]   # platform -> url
        deps = (),
        external_deps = (),
        tests = (),
        visibility = None):
    # We don't need duplicate targets if we have multiple usage of URLs
    urls = collections.uniq(platform_urls.values())
    wheel_targets = {}  # Dict[str, str]      # url -> prebuilt_target_name

    compiled = False

    # Setup all the remote_file and prebuilt_python_library targets
    # urls have #sha1=<sha1> at the end.
    for url in urls:
        if url == None:
            continue
        if _is_compiled(url):
            compiled = True
        orig_url, _, sha1 = url.rpartition("#sha1=")
        if not sha1:
            fail("There is no #sha1= tag on the end of URL: " + url)

        # Opensource usage of this may have #md5 tags from pypi
        wheel = _get_url_basename(orig_url)
        target_name = _remote_wheel(url, wheel, sha1, visibility)
        target_name = _prebuilt_target(wheel, target_name, visibility)
        wheel_targets[url] = target_name

    attrs = {}

    # Create the ability to override the platform that wheels use
    wheel_platform = native.read_config("python", "wheel_platform_override")

    # Use platform_deps to rely on the correct wheel target for
    # each platform
    platform_deps = [
        ("{}$".format(platform_utils.escape(py_platform)), None if (url == None) else [wheel_targets[url]])
        for py_platform, url in sorted(platform_urls.items())
        # Some platforms just do not have wheels available. In this case, we remove
        # that platform from platform deps. You just won't get a whl on those
        # platforms. HOWEVER: Due to how platforms work in buck, if there's a
        # wheel_platform, we want to keep this platform. We keep it because a user
        # might still get something like 'gcc5-blah' as the buck native platform
        # even when we've overwritten all urls with say a mac specific url.
        # It sucks, and when select() and platform support is in buck and handled
        # properly by all rules, this will be wholly re-evaluated.
        if url or wheel_platform
    ]

    if wheel_platform:
        platform_deps = _override_wheels(platform_deps, wheel_platform)

    # This is to work around how buck instantiates toolchains. Without this,
    # we don't always end up properly instantiating the c++ toolchains if
    # the compiler is a python script. T34675852
    cpp_genrule_name = version + "-genrule-hack"
    fb_native.cxx_genrule(
        name = cpp_genrule_name,
        out = "dummy",
        cmd = "echo '' > $OUT",
    )
    deps = (deps or []) + [":" + cpp_genrule_name]

    if external_deps:
        if compiled:
            attrs["exclude_deps_from_merged_linking"] = True
        platform_deps.extend(
            src_and_dep_helpers.format_platform_deps(
                [
                    src_and_dep_helpers.normalize_external_dep(d, lang_suffix = "-py")
                    for d in external_deps
                ],
            ),
        )

    if tests:
        attrs["tests"] = tests

    # TODO: Figure out how to handle typing info from wheels
    if get_typing_config_target():
        gen_typing_config(version, visibility = visibility)
    fb_native.python_library(
        name = version,
        deps = deps,
        platform_deps = platform_deps,
        visibility = get_visibility(visibility, version),
        **attrs
    )
