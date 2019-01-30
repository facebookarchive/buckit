"""
An `image_layer` is an `image_feature` with some additional parameters.  Its
purpose to materialize that `image_feature` as a btrfs subvolume in the
per-repo `buck-image/out/volume/targets`.

We call the subvolume a "layer" because it can be built on top of a snapshot
of its `parent_layer`, and thus can be represented as a btrfs send-stream for
more efficient storage & distribution.

The Buck output of an `image_layer` target is a JSON file with information
on how to find the resulting layer in the per-repo
`buck-image/out/volume/targets`.  See `SubvolumeOnDisk.to_json_file`.

## Implementation notes

The implementation of this converter deliberately minimizes the amount of
business logic in its command.  The converter must include **only** our
interactions with the buck target graph.  Everything else should be
delegated to subcommands.

### Command

In composing the `bash` command, our core maxim is: make it a hermetic
function of the converter's inputs -- do not read data from disk, do not
insert disk paths into the command, do not do anything that might cause the
bytes of the command to vary between machines or between runs.  To achieve
this, we use Buck macros to resolve all paths, including those to helper
scripts.  We rely on environment variables or pipes to pass data between the
helper scripts.

Another reason to keep this converter minimal is that `buck test` cannot
make assertions about targets that fail to build.  Since we only have the
ability to test the "good" targets, it behooves us to put most logic in
external scripts, so that we can unit-test its successes **and** failures
thoroughly.

### Output

We mark `image_layer` uncacheable, because there's no easy way to teach Buck
to serialize a btrfs subvolume (for that, we have `image_layer_sendstream`).
That said, we should still follow best practices to avoid problems if e.g.
the user renames their repo, or similar.  These practices include:
  - The output JSON must store no absolute paths.
  - Store Buck target paths instead of paths into the output directory.

### Dependency resolution

An `image_layer` consumes `image_feature` outputs to decide what to put into
the btrfs subvolume.  These outputs are actually just JSON files that
reference other targets, and do not contain the data to be written into the
image.

Therefore, `image_layer` has to explicitly tell buck that it needs all
direct dependencies of its `image_feature`s to be present on disk -- see our
`attrfilter` queries below.  Without this, Buck would merrily fetch the just
the `image_feature` JSONs from its cache, and not provide us with any of the
buid artifacts that comprise the image.

We do NOT need the direct dependencies of the parent layer's features,
because we treat the parent layer as a black box -- whatever it has laid
down in the image, that's what it provides (and we don't care about how).
The consequences of this information hiding are:

  - Better Buck cache efficiency -- we don't have to download
    the dependencies of the ancestor layers' features. Doing that would be
    wasteful, since those bits are redundant with what's in the parent.

  - Ability to use foreign image layers / apply non-pure post-processing to
    a layer.  In terms of engineering, both of these non-pure approaches are
    a terrible idea and a maintainability headache, but they do provide a
    useful bridge for transitioning to Buck image builds from legacy
    imperative systems.

  - The image compiler needs a litte extra code to walk the parent layer and
    determine what it provides.

  - We cannot have "unobservable" dependencies between features.  Since
    feature dependencies are expected to routinely cross layer boundaries,
    feature implementations are forced only to depend on data that can be
    inferred from the filesystem -- since this is all that the parent layer
    implementation can do.  NB: This is easy to relax in the future by
    writing a manifest with additional metadata into each layer, and using
    that metadata during compilation.
"""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs:config.bzl", "config")
load(
    "@fbcode_macros//build_defs:custom_rule.bzl",
    "get_project_root_from_gen_dir",
)
load("@fbcode_macros//build_defs:native_rules.bzl", "buck_genrule")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load(
    "//fs_image/buck:image_feature.bzl",
    "DO_NOT_DEPEND_ON_FEATURES_SUFFIX",
    "image_feature",
)
load(":image_utils.bzl", "image_utils")

def _get_fbconfig_rule_type():
    return "image_layer"

def image_layer(
        name = None,
        # The name of another `image_layer` target, on top of which the
        # current layer will install its features.
        parent_layer = None,
        # Future: should we determine this dynamically from the installed
        # artifacts (by totaling up the bytes needed for copied files, RPMs,
        # tarballs, etc)?  NB: At the moment, this number doesn't work
        # precisely as a user would want -- we just require that the base
        # volume have at least this much space, -- but hopefully people
        # don't have to change it too much.
        # The string is used instead of int because build language supports
        # only 32-bit integer values.
        layer_size_bytes = "100" + "0" * 9,
        visibility = None,
        # Path to a binary target, with this CLI signature:
        #   yum_from_repo_snapshot --install-root PATH -- SOME YUM ARGS
        # Required if any dependent `image_feature` specifies `rpms`.
        yum_from_repo_snapshot = None,
        # Path to a target outputting a btrfs send-stream of a subvolume;
        # mutually exclusive with using any of the image_feature fields.
        from_sendstream = None,
        # The name of the btrfs subvolume to create.
        subvol_name = "volume",
        **image_feature_kwargs):
    visibility = get_visibility(visibility, name)

    # There are two independent ways to populate the resulting btrfs
    # subvolume: (i) set `from_sendstream` and nothing else, (ii) set other
    # arguments as desired.  These modes live in a single target type for
    # memorability, and because much of the implementation is shared.
    if from_sendstream != None:
        if image_feature_kwargs or yum_from_repo_snapshot:
            fail(
                "cannot use `from_sendstream` with `image_feature` args " +
                "or with `yum_from_repo_snapshot`",
            )
        if parent_layer != None:
            # Mechanistically, applying a send-stream on top of an
            # existing layer is just a regular `btrfs receive`.
            # However, the rules in the current `receive` implementation
            # for matching the parent to the stream are kind of awkward,
            # and it's not clear whether they are right for us in Buck.
            fail("Not implemented")
        make_subvol_cmd = '''
            sendstream_path=$(location {from_sendstream})
            # CAREFUL: To avoid inadvertently masking errors, we only
            # perform command substitutions with variable assignments.
            sendstream_path=\\$(readlink -f "$sendstream_path")
            subvol_name=\\$(
                cd "$subvolumes_dir/$subvolume_wrapper_dir"
                sudo btrfs receive -f "$sendstream_path" . >&2
                subvol=$(ls)
                test 1 -eq $(echo "$subvol" | wc -l)  # Expect 1 subvolume
                # Receive should always mark the result read-only.
                test $(sudo btrfs property get -ts "$subvol" ro) = ro=true
                echo "$subvol"
            )
            # `exe` vs `location` is explained in `image_package.py`
            $(exe //fs_image/compiler:subvolume-on-disk) \
              "$subvolumes_dir" \
              "$subvolume_wrapper_dir/$subvol_name" > "$OUT"
        '''.format(from_sendstream = from_sendstream)
    else:
        make_subvol_cmd = _compile_image_features(
            base_path = native.package_name(),
            rule_name = name,
            parent_layer = parent_layer,
            image_feature_kwargs = image_feature_kwargs,
            yum_from_repo_snapshot = yum_from_repo_snapshot,
            subvol_name = subvol_name,
        )

    buck_genrule(
        name = name,
        out = name + ".json",
        type = _get_fbconfig_rule_type(),  # For queries
        # Layers are only usable on the same host that built them, so
        # keep our output JSON out of the distributed Buck cache.  See
        # the docs for BuildRule::isCacheable.
        cacheable = False,
        bash = image_utils.wrap_bash_build_in_common_boilerplate(
            self_dependency = "//fs_image/buck:image_layer",
            bash = '''
            # We want subvolume names to be user-controllable. To permit
            # this, we wrap each subvolume in a temporary subdirectory.
            # This also allows us to prevent access to capability-
            # escalating programs inside the built subvolume by users
            # other than the repo owner.
            #
            # The "version" code here ensures that the wrapper directory
            # has a unique name.  We could use `mktemp`, but our variant
            # is a little more predictable (not a security concern since
            # we own the parent directory) and a lot more debuggable.
            # Usability is better since our version sorts by build time.
            #
            # `exe` vs `location` is explained in `image_package.py`.
            # `exe` won't expand in \\$( ... ), so we need `binary_path`.
            binary_path=( $(exe //fs_image:subvolume-version) )
            subvolume_ver=\\$( "${{binary_path[@]}}" )
            subvolume_wrapper_dir={rule_name_quoted}":$subvolume_ver"

            # IMPORTANT: This invalidates and/or deletes any existing
            # subvolume that was produced by the same target.  This is the
            # point of no return.
            #
            # This creates the wrapper directory for the subvolume, and
            # pre-initializes "$OUT" in a special way to support a form of
            # refcounting that distinguishes between subvolumes that are
            # referenced from the Buck cache ("live"), and ones that are
            # no longer referenced ("dead").  We want to create the
            # refcount file before starting the build to guarantee that we
            # have refcount files for partially built images -- this makes
            # debugging failed builds a bit more predictable.
            refcounts_dir=\\$( readlink -f {refcounts_dir_quoted} )
            # `exe` vs `location` is explained in `image_package.py`
            $(exe //fs_image:subvolume-garbage-collector) \
              --refcounts-dir "$refcounts_dir" \
              --subvolumes-dir "$subvolumes_dir" \
              --new-subvolume-wrapper-dir "$subvolume_wrapper_dir" \
              --new-subvolume-json "$OUT"

            {make_subvol_cmd}
            '''.format(
                rule_name_quoted = shell.quote(name),
                refcounts_dir_quoted = paths.join(
                    "$GEN_DIR",
                    shell.quote(get_project_root_from_gen_dir()),
                    "buck-out/.volume-refcount-hardlinks/",
                ),
                make_subvol_cmd = make_subvol_cmd,
            ),
            volume_min_free_bytes = layer_size_bytes,
            log_description = "{}(name={})".format(
                _get_fbconfig_rule_type(),
                name,
            ),
        ),
        visibility = visibility,
    )

def _compile_image_features(
        base_path,
        rule_name,
        parent_layer,
        image_feature_kwargs,
        yum_from_repo_snapshot,
        subvol_name):
    # For ease of use, a layer takes all the arguments of a feature, so
    # just make an implicit feature target to implement this.
    feature_name = rule_name + "-feature"
    feature_target = \
        ":" + feature_name + DO_NOT_DEPEND_ON_FEATURES_SUFFIX
    image_feature(
        name = feature_name,
        **image_feature_kwargs
    )

    # We will ask Buck to ensure that the outputs of the direct dependencies
    # of our `image_feature`s are available on local disk.
    #
    # See `Implementation notes: Dependency resolution` in `__doc__` -- note
    # that we need no special logic to exclude parent-layer features, since
    # this query does not traverse them anyhow.
    dep_features_query = "attrfilter(type, image_feature, deps({}))".format(
        feature_target,
    )

    return '''
        {maybe_yum_from_repo_snapshot_dep}
        # Take note of `targets_and_outputs` below -- this enables the
        # compiler to map the `__BUCK_TARGET`s in the outputs of
        # `image_feature` to those targets' outputs.
        #
        # `exe` vs `location` is explained in `image_package.py`.
        $(exe //fs_image:compiler) \
          --subvolumes-dir "$subvolumes_dir" \
          --subvolume-rel-path \
            "$subvolume_wrapper_dir/"{subvol_name_quoted} \
          --parent-layer-json {parent_layer_json_quoted} \
          {maybe_quoted_yum_from_repo_snapshot_args} \
          --child-layer-target {current_target_quoted} \
          --child-feature-json $(location {my_feature_target}) \
          --child-dependencies \
            $(query_targets_and_outputs 'deps({dep_features_query}, 1)') \
              > "$OUT"
    '''.format(
        subvol_name_quoted = shell.quote(subvol_name),
        parent_layer_json_quoted = "$(location {})".format(parent_layer) if parent_layer else "''",
        current_target_quoted = shell.quote(target_utils.to_label(
            config.get_current_repo_name(),
            base_path,
            rule_name,
        )),
        my_feature_target = feature_target,
        dep_features_query = dep_features_query,
        maybe_quoted_yum_from_repo_snapshot_args = "" if not yum_from_repo_snapshot else
        # In terms of **dependency** structure, we want this
        # to be `exe` (see `image_package.py` for why).
        # However the string output of the `exe` macro may
        # actually be a shell snippet, which would break
        # here.  To work around this, we add a no-op $(exe)
        # dependency via `maybe_yum_from_repo_snapshot_dep`.
        "--yum-from-repo-snapshot $(location {})".format(
            yum_from_repo_snapshot,
        ),
        maybe_yum_from_repo_snapshot_dep = "" if not yum_from_repo_snapshot else "echo $(exe {}) > /dev/null".format(
            yum_from_repo_snapshot,
        ),
    )
