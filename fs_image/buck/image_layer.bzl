"""
An `image.layer` is an `image.feature` with some additional parameters.  Its
purpose to materialize that `image.feature` as a btrfs subvolume in the
per-repo `buck-image/out/volume/targets`.

We call the subvolume a "layer" because it can be built on top of a snapshot
of its `parent_layer`, and thus can be represented as a btrfs send-stream for
more efficient storage & distribution.

The Buck output of an `image.layer` target is a JSON file with information
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

We mark `image.layer` uncacheable, because there's no easy way to teach Buck
to serialize a btrfs subvolume (for that, we have `image.package`).

That said, we should still follow best practices to avoid problems if e.g.
the user renames their repo, or similar.  These practices include:
  - The output JSON must store no absolute paths.
  - Store Buck target paths instead of paths into the output directory.

### Dependency resolution

An `image.layer` consumes `image.feature` outputs to decide what to put into
the btrfs subvolume.  These outputs are actually just JSON files that
reference other targets, and do not contain the data to be written into the
image.

Therefore, `image.layer` has to explicitly tell buck that it needs all
direct dependencies of its `image.feature`s to be present on disk -- see our
`attrfilter` queries below.  Without this, Buck would merrily fetch the just
the `image.feature` JSONs from its cache, and not provide us with any of the
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
load("@bazel_skylib//lib:types.bzl", "types")
load("@fbcode_macros//build_defs:config.bzl", "config")
load(
    "@fbcode_macros//build_defs:custom_rule.bzl",
    "get_project_root_from_gen_dir",
)
load("@fbcode_macros//build_defs:native_rules.bzl", "buck_command_alias", "buck_genrule")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load(
    "//fs_image/buck:image_feature.bzl",
    "DO_NOT_DEPEND_ON_FEATURES_SUFFIX",
    "image_feature",
)
load(":artifacts_require_repo.bzl", "built_artifacts_require_repo")
load(":image_source.bzl", "image_source")
load(":image_utils.bzl", "image_utils")

def _get_fbconfig_rule_type():
    return "image_layer"

def _build_opts(
        # The name of the btrfs subvolume to create.
        subvol_name = "volume",
        # Path to a binary target, with this CLI signature:
        #   yum_from_repo_snapshot --install-root PATH -- SOME YUM ARGS
        # Mutually exclusive with build_appliance: either
        # yum_from_repo_snapshot or build_appliance is required
        # if any dependent `image_feature` specifies `rpms`.
        yum_from_repo_snapshot = None,
        # Path to a target outputting a btrfs send-stream of a build appliance:
        # a self-contained file tree with /yum-from-snapshot and other tools
        # like btrfs, yum, tar, ln used for image builds along with all
        # their dependencies (but /usr/local/fbcode).  Mutually exclusive
        # with yum_from_repo_snapshot: either build_appliance or
        # yum_from_repo_snapshot is required if any dependent
        # `image_feature` specifies `rpms`.
        build_appliance = None):
    return struct(
        subvol_name = subvol_name,
        yum_from_repo_snapshot = yum_from_repo_snapshot,
        build_appliance = build_appliance,
    )

def _bare_image_layer(
        name = None,
        # The name of another `image_layer` target, on top of which the
        # current layer will install its features.
        parent_layer = None,
        # List of `image.feature` target paths and/or nameless structs from
        # `image.feature`.  Mutually exclusive with `from_sendstream`.
        features = None,
        # A struct containing fields accepted by `_build_opts` above.
        # Usable only with `features`.
        build_opts = None,
        # `image.source` (see `image_source.bzl`) or path to a target
        # outputting a btrfs send-stream of a subvolume; mutually exclusive
        # with `features`.
        from_sendstream = None,
        # Layers can be used in the `mounts` field of an `image.feature`.
        # This setting affects how **this** layer may be mounted inside
        # others.
        #
        # The default mount config for a layer only provides a
        # `build_source`, specifying how the layer should be mounted at
        # development time inside the in-repo `buck-image-out` subtree.
        #
        # This argument can set `runtime_source` and `default_mountpoint`.
        # The former is essential -- to get a layer from `mounts` to be
        # mounted at container run-time, we have to tell the container agent
        # how to obtain the layer-to-be-mounted.  This can be done in a
        # variety of ways, so it's not part of `image.layer` itself, and
        # must be set from outside.
        mount_config = None,
        # Most use-cases should never need to set this.  A string is used
        # instead of int because Skylark supports only 32-bit integers.
        # Future:
        #  (i) Should we determine this dynamically from the installed
        #      artifacts (by totaling up the bytes needed for copied files,
        #      RPMs, tarballs, etc)?  NB: At the moment, this number doesn't
        #      work precisely as a user would want -- we just require that
        #      the base volume have at least this much space, -- but
        #      hopefully people don't have to change it too much.
        # (ii) For sendstreams, it's much more plausible to correctly
        #      estimate the size requirements, so we might do that sooner.
        layer_size_bytes = "100" + "0" * 9,
        visibility = None):
    visibility = get_visibility(visibility, name)
    current_target = target_utils.to_label(
        config.get_current_repo_name(),
        native.package_name(),
        name,
    )

    # There are two mutually exclusive ways to populate the resulting btrfs
    # subvolume: (i) set `from_sendstream`, (ii) set `build`.  These modes
    # live in a single target type for memorability, and because the entire
    # API of the resulting target, and much of the implementation is shared.
    if from_sendstream:
        from_sendstream = image_source(from_sendstream)
        if features or build_opts:
            fail("cannot use `from_sendstream` with `features` or `build_opts`")
        if parent_layer != None:
            # Mechanistically, applying a send-stream on top of an existing
            # layer is just a regular `btrfs receive`.  However, the rules
            # in the current `receive` implementation for matching the
            # parent to the stream are kind of awkward, and it's not clear
            # whether they are right for us in Buck.
            fail("Not implemented")
        make_subvol_cmd = '''
            {set_base_path}
            sendstream_path="$base_path"{maybe_quoted_path}
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
              "$subvolume_wrapper_dir/$subvol_name" > "$layer_json"
        '''.format(
            maybe_quoted_path = (
                "/" + shell.quote(from_sendstream.path)
            ) if from_sendstream.path else "",
            set_base_path = "base_path=$(location {})".format(
                from_sendstream.source,
            ) if from_sendstream.source else '''\
            # `exe` vs `location` is explained in `image_package.py`.
            # `exe` won't expand in \\$( ... ), so we need `binary_path`.
            binary_path=( $(exe //fs_image:find-built-subvol) )
            layer_path=$(location {})
            base_path=\\$( "${{binary_path[@]}}" "$layer_path" )
            '''.format(from_sendstream.layer),
        )
    else:  # Build a new layer. It may be empty.
        make_subvol_cmd = _compile_image_features(
            current_target = current_target,
            parent_layer = parent_layer,
            features = features,
            build_opts = _build_opts(**(
                build_opts._asdict() if build_opts else {}
            )),
        )

    if mount_config == None:
        mount_config = {}
    for key in ("build_source", "is_directory"):
        if key in mount_config:
            fail("`{}` cannot be customized".format(key), "mount_config")
    mount_config["is_directory"] = True
    mount_config["build_source"] = {
        "source": current_target,
        # The compiler knows how to resolve layer locations.  For now, we
        # don't support mounting a subdirectory of a layer because that
        # might make packaging more complicated, but it could be done.
        "type": "layer",
    }

    buck_genrule(
        name = name,
        out = "layer",
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
            subvolume_wrapper_dir={layer_name_quoted}":$subvolume_ver"

            # Do not touch $OUT until the very end so that if we
            # accidentally exit early with code 0, the rule still fails.
            mkdir "$TMP/out"
            echo {quoted_mountconfig_json} > "$TMP/out/mountconfig.json"
            # "layer.json" points at the subvolume inside `buck-image-out`.
            layer_json="$TMP/out/layer.json"

            # IMPORTANT: This invalidates and/or deletes any existing
            # subvolume that was produced by the same target.  This is the
            # point of no return.
            #
            # This creates the wrapper directory for the subvolume, and
            # pre-initializes "$layer_json" in a special way to support a
            # form of refcounting that distinguishes between subvolumes that
            # are referenced from the Buck cache ("live"), and ones that are
            # no longer referenced ("dead").  We want to create the refcount
            # file before starting the build to guarantee that we have
            # refcount files for partially built images -- this makes
            # debugging failed builds a bit more predictable.
            refcounts_dir=\\$( readlink -f {refcounts_dir_quoted} )
            # `exe` vs `location` is explained in `image_package.py`
            $(exe //fs_image:subvolume-garbage-collector) \
                --refcounts-dir "$refcounts_dir" \
                --subvolumes-dir "$subvolumes_dir" \
                --new-subvolume-wrapper-dir "$subvolume_wrapper_dir" \
                --new-subvolume-json "$layer_json"

            {make_subvol_cmd}

            mv "$TMP/out" "$OUT"  # Allow the rule to succeed.
            '''.format(
                layer_name_quoted = shell.quote(name),
                refcounts_dir_quoted = paths.join(
                    "$GEN_DIR",
                    shell.quote(get_project_root_from_gen_dir()),
                    "buck-out/.volume-refcount-hardlinks/",
                ),
                make_subvol_cmd = make_subvol_cmd,
                # To make layers "image-mountable", provide `mountconfig.json`.
                quoted_mountconfig_json = shell.quote(
                    struct(**mount_config).to_json(),
                ),
            ),
            volume_min_free_bytes = layer_size_bytes,
            log_description = "{}(name={})".format(
                _get_fbconfig_rule_type(),
                name,
            ),
        ),
        # Layers are only usable on the same host that built them, so
        # keep our output JSON out of the distributed Buck cache.  See
        # the docs for BuildRule::isCacheable.
        cacheable = False,
        type = _get_fbconfig_rule_type(),  # For queries
        visibility = visibility,
    )

def _query_set(target_paths):
    'Returns `set("//foo:target1" "//bar:target2")` for use in Buck queries.'

    if not target_paths:
        return "set()"

    # This does not currently escape double-quotes since Buck docs say they
    # cannot occur: https://buck.build/concept/build_target.html
    return 'set("' + '" "'.join(target_paths) + '")'

def _compile_image_features(
        current_target,
        parent_layer,
        features,
        build_opts):
    if features == None:
        features = []
    feature_targets = []
    direct_deps = []
    inline_feature_dicts = []
    for f in features:
        if types.is_string(f):
            feature_targets.append(f + DO_NOT_DEPEND_ON_FEATURES_SUFFIX)
        else:
            direct_deps.extend(f.deps)
            inline_feature_dicts.append(f.items._asdict())
            inline_feature_dicts[-1]["target"] = current_target

    return '''
        {maybe_yum_from_repo_snapshot_dep}
        # Take note of `targets_and_outputs` below -- this enables the
        # compiler to map the `__BUCK_TARGET`s in the outputs of
        # `image_feature` to those targets' outputs.
        #
        # `exe` vs `location` is explained in `image_package.py`.
        $(exe //fs_image:compiler) {maybe_artifacts_require_repo} \
          --subvolumes-dir "$subvolumes_dir" \
          --subvolume-rel-path \
            "$subvolume_wrapper_dir/"{subvol_name_quoted} \
          --parent-layer-json {parent_layer_json_quoted} \
          {maybe_quoted_build_appliance_args} \
          {maybe_quoted_yum_from_repo_snapshot_args} \
          --child-layer-target {current_target_quoted} \
          {quoted_child_feature_json_args} \
          --child-dependencies {feature_deps_query_macro} \
              > "$layer_json"
    '''.format(
        subvol_name_quoted = shell.quote(build_opts.subvol_name),
        parent_layer_json_quoted = "$(location {})/layer.json".format(
            parent_layer,
        ) if parent_layer else "''",
        current_target_quoted = shell.quote(current_target),
        quoted_child_feature_json_args = " ".join([
            "--child-feature-json $(location {})".format(t)
            for t in feature_targets
        ] + (
            ["--child-feature-json <(echo {})".format(shell.quote(struct(
                target = current_target,
                features = inline_feature_dicts,
            ).to_json()))] if inline_feature_dicts else []
        )),
        # We will ask Buck to ensure that the outputs of the direct
        # dependencies of our `image_feature`s are available on local disk.
        #
        # See `Implementation notes: Dependency resolution` in `__doc__` --
        # note that we need no special logic to exclude parent-layer
        # features, since this query does not traverse them anyhow.
        #
        # We have two layers of quoting here.  The outer '' groups the query
        # into a single argument for `query_targets_and_outputs`.  Then,
        # `_query_set` double-quotes each target name to allow the use of
        # special characters like `=` in target names.
        feature_deps_query_macro = """$(query_targets_and_outputs '
            {direct_deps_set} union
            deps(attrfilter(type, image_feature, deps({feature_set})), 1)
        ')""".format(
            # For inline `image.feature`s, we already know the direct deps.
            direct_deps_set = _query_set(direct_deps),
            # We will query the direct deps of the features that are targets.
            feature_set = _query_set(feature_targets),
        ),
        maybe_artifacts_require_repo = (
            "--artifacts-may-require-repo" if
            # Future: Consider **only** emitting this flag if the image is
            # actually contains executables (via `install_executable`).
            # NB: This may not actually be 100% doable at macro parse time,
            # since `install_executable_tree` does not know if it is
            # installing an executable file or a data file until build-time.
            # That said, the parse-time test would already narrow the scope
            # when the repo is mounted, and one could potentially extend the
            # compiler to further modulate this flag upon checking whether
            # any executables were in fact installed.
            built_artifacts_require_repo() else ""
        ),
        maybe_quoted_build_appliance_args = (
            "--build-appliance-json $(location {})/layer.json".format(
                build_opts.build_appliance,
            ) if build_opts.build_appliance else ""
        ),
        maybe_quoted_yum_from_repo_snapshot_args = (
            # In terms of **dependency** structure, we want this to be `exe`
            # (see `image_package.py` for why).  However the string output
            # of the `exe` macro may actually be a shell snippet, which
            # would break here.  To work around this, we add a no-op $(exe)
            # dependency via `maybe_yum_from_repo_snapshot_dep`.
            "--yum-from-repo-snapshot $(location {})".format(
                build_opts.yum_from_repo_snapshot,
            ) if build_opts.yum_from_repo_snapshot else ""
        ),
        maybe_yum_from_repo_snapshot_dep = (
            # Building the layer has a runtime depepndency on the yum
            # target.  We don't need this for `build_appliance` because any
            # @mode/dev executables inside a layer should already have been
            # wrapped via `wrap_runtime_deps`.
            "echo $(exe {}) > /dev/null".format(
                build_opts.yum_from_repo_snapshot,
            ) if build_opts.yum_from_repo_snapshot else ""
        ),
    )

def _add_run_in_subvol_target(name, kind, layer_ext = ""):
    buck_command_alias(
        name = name + "-" + kind,
        args = ["--layer", "$(location {})".format(":" + name + layer_ext)] + (
            ["--boot"] if kind == "boot" else []
        ),
        exe = "//fs_image:nspawn-run-in-subvol",
        visibility = [],
    )

def image_layer(
        name = None,
        # Used to identify that this layer can be booted and will trigger
        # the generation of a `-boot` target.
        enable_boot_target = False,
        **image_layer_kwargs):
    """
    Wrap the the creation of the image layer to allow users to interact
    with the constructed subvol using `buck run //path/to:layer-{container,boot}`.
    Most of the user documentation is on `_bare_image_layer()`.
    """
    _bare_image_layer(name = name, **image_layer_kwargs)

    # Add the `-container` run target
    _add_run_in_subvol_target(name, "container")

    if enable_boot_target:
        _add_run_in_subvol_target(name, "boot")
