load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")

TEST_TARGET_PREFIX = "//fs_image/compiler/tests:"

def READ_MY_DOC_image_feature_target(name):
    """
    DANGER: If you depend on a feature target for testing, you MUST manually
    add any `image_feature` targets that it depends on to your `deps = []`.
    If you fail to do this, Buck will not know to rebuild the the test if
    one of its indirect `image_feature` dependencies changes.  See
    `image_feature.py` for an explanation.
    """

    # TODO: Just use a proper visibility rule?
    return name + (
        "_IF_YOU_REFER_TO_THIS_RULE_YOUR_DEPENDENCIES_WILL_BE_BROKEN_" +
        "SO_DO_NOT_DO_THIS_EVER_PLEASE_KTHXBAI"
    )

def image_feature_python_unittest(test_image_feature_transitive_deps, deps = None, **kwargs):
    env = {
        "test_image_feature_path_to_" + t: "$(location {})".format(
            TEST_TARGET_PREFIX + t,
        )
        for t in test_image_feature_transitive_deps
    }
    deps = (deps or []) + [":sample_items"]

    # For now cpp_deps is raw buck deps for python_ targets
    cpp_deps = [
        TEST_TARGET_PREFIX + t
        for t in test_image_feature_transitive_deps
    ]
    return python_unittest(
        base_module = "compiler",
        env = env,
        # The test reads `feature.json`, so we need actual files on disk.
        par_style = "zip",
        deps = deps,
        cpp_deps = cpp_deps,
        **kwargs
    )
