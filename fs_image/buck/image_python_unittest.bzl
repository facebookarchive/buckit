load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load(
    ":image_unittest_helpers.bzl",
    "get_disabletest_name",
    "get_disabletest_tags",
    "get_test_wrapper_kwargs",
    "outer_wrapper_test",
)

def image_python_unittest(
        name,
        layer,
        run_as_user = "nobody",
        visibility = None,
        par_style = None,
        **python_unittest_kwargs):
    visibility = get_visibility(visibility, name)
    wrapper_kwargs = get_test_wrapper_kwargs(python_unittest_kwargs)

    # `par_style` only applies to the inner test that runs the actual user
    # code, because there is only one working choice for the outer test.
    # For the inner test:
    #   - Both `zip` and `fastzip` are OK, but the latter is the default
    #     since it should be more kind to `/tmp` `tmpfs` memory usage.
    #   - XAR fails to work for tests that run unprivileged (the default)
    #     My quick/failed attempt to fix this is in P61015086, but we'll
    #     probably be better off adding support for copying python trees
    #     directly into the image in preference to fixing XAR.
    if par_style == None:
        # People who need to access the filesystem will have to set "zip",
        # but that'll cost more RAM to run since nspawn `/tmp` is `tmpfs`.
        par_style = "fastzip"
    elif par_style == "xar":
        fail(
            "`image.python_unittest` does not support this due to XAR " +
            "limitations (see the in-code docs)",
            "par_style",
        )

    python_unittest(
        name = get_disabletest_name(name),
        tags = get_disabletest_tags(),
        par_style = par_style,
        visibility = visibility,
        **python_unittest_kwargs
    )

    outer_wrapper_test(
        name,
        layer,
        run_as_user,
        visibility,
        "//fs_image/buck:image_python_unittest",
        wrapper_kwargs,
    )
