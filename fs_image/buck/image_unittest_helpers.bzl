load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs:native_rules.bzl", "buck_genrule")
load("@fbcode_macros//build_defs:python_library.bzl", "python_library")
load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")
load(":image_layer.bzl", "image_layer")

def get_disabletest_name(name):
    # This is the test binary that is supposed to run inside the image.  The
    # "IGNORE-ME" prefix serves to inform users who come across this target
    # that this is not the test binary they are looking for.  It's a prefix
    # to avoid people stumbling across it via tab-completion.
    return "IGNORE-ME-layer-test--" + name

def get_disabletest_tags():
    # These tags (aka labels) are a defense-in-depth attempt to make the
    # un-wrapped test never get executed by the test runner.
    return [
        # In `.buckconfig`, we have a line that asks Buck not to report
        # this test to the test runner if it's only being pulled in as a
        # transitive dependency:
        #
        #   [test]
        #     excluded_labels = exclude_test_if_transitive_dep
        #
        # This means that with `buck test //path:name`, the test runner
        # would never see IGNORE-ME tests.
        "exclude_test_if_transitive_dep",
        # Buck will still report the test to the test runner if the
        # user runs `buck test path/...`, which is a common pattern.
        # This tag tells the FB test runner NOT to run this test, nor to
        # show it as OMITTED.
        "test_is_invisible_to_testpilot",
        # For peace of mind, add classic test-runner tags that are
        # mutually incompatible, and would essentially always cause the
        # test to be marked OMITTED even if the prior two tags were
        # somehow ignored.
        "disabled",
        "local_only",
        "extended",
        "slow",
    ]

def get_test_wrapper_kwargs(unittest_kwargs):
    # Some kwargs need to be set on the wrapper instead
    # of the actual test (to be wrapped).
    wrapper_kwargs = {"tags": []}
    for kwarg_name in ("tags", "needed_coverage"):
        if kwarg_name in unittest_kwargs:
            wrapper_kwargs[kwarg_name] = unittest_kwargs.pop(kwarg_name)
    return wrapper_kwargs

def outer_wrapper_test(
        name,
        layer,
        run_as_user,
        visibility,
        this_bzl_file,
        wrapper_kwargs):
    # Make a test-specific image containing the test binary.
    binary_path = "/layer-test-binary"

    # This target name gets a suffix to keep it discoverable via tab-completion
    test_layer = name + "--test-layer"
    test_name = get_disabletest_name(name)
    image_layer(
        name = test_layer,
        install_executables = {(":" + test_name): binary_path},
        parent_layer = layer,
        visibility = visibility,
    )

    # Generate a `.py` file that sets some of the key container options.
    test_spec_py = "layer-test-spec-py-" + name
    buck_genrule(
        name = test_spec_py,
        out = "unused_name.py",
        bash = 'echo {} > "$OUT"'.format(shell.quote((
            "def nspawn_in_subvol_args():\n" +
            "    return {args}\n"
        ).format(
            args = repr(["--user", run_as_user, "--", binary_path]),
        ))),
        visibility = visibility,
    )

    # The `.py` file with container options must be in its own library
    # because the base_module of `nspawn_test_in_subvol.py` is empty, and
    # this library allows us to place the packaged spec file (and layer) at
    # the root of the source archive.  That makes the much easier to for
    # `nspawn_test_in_subvol` to discover than if it had to contend with a
    # user-supplied `base_module` as is set on the `name` target.
    test_spec_lib = "layer-test-spec-" + name
    python_library(
        name = test_spec_lib,
        srcs = {":" + test_spec_py: "__image_python_unittest_spec__.py"},
        base_module = "",
        # `nspawn_test_in_subvol` knows to look for this file in the archive.
        resources = {":" + test_layer: "nspawn-in-test-subvol-layer"},
        visibility = visibility,
    )

    # This **has** to be a `python_unittest` (as opposed to e.g. a `sh_test`
    # with the right `labels`) so that `needed_coverage` works as expected.
    # Moreover, it's overall cleaner to make the wrapper be the same rule
    # type as the wrapped test.
    python_unittest(
        name = name,
        resources = {
            # Allow CI determinators to discover that tests need to be
            # rebuilt if this .bzl file changes.
            this_bzl_file: "_unused_rsrc_for_bzl_dep",
            # This "porcelain" target `name` already has 5-hop dependency on
            # the "plumbing" target `test_name`, which actually contains the
            # source files for the test.  We add this redundant dummy
            # dependency to aid CI dependency resolution -- our current
            # heuristics consider targets that are far away from the changed
            # source code in terms of dependency hops to be lower priority
            # to run.  But the current target is the only real way to
            # execute the source, so we must ensure it's not far from the
            # source files in the dependency graph.  This puts us at 1 hop.
            ":" + test_name: "_unused_rsrc_for_test_sources",
            # Same rationale as for the dependency on `:test_name` -- we
            # don't want to be too many hops away from any source code
            # included in the layer being tested.
            layer: "_unused_rsrc_for_layer",
        },
        main_module = "nspawn_test_in_subvol",
        deps = [
            # NB: It's possible to use `env` to pass the arguments and the
            # location of the test layer to the driver binary.  However,
            # this would prevent one from running the test binary directly,
            # bypassing Buck.  Since Buck CLI is slow, this would be a
            # significant drop in usability, so we use this library trick.
            ":" + test_spec_lib,
            "//fs_image:nspawn-test-in-subvol-library",
        ],
        # Ensures we can read resources in @mode/opt.  "xar" cannot work
        # because `root` cannot access the content of unprivileged XARs.
        par_style = "zip",
        visibility = visibility,
        **wrapper_kwargs
    )
