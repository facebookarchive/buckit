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
load("@fbcode_macros//build_defs:config.bzl", "config")
load(
    "@fbcode_macros//build_defs:custom_rule.bzl",
    "get_project_root_from_gen_dir",
)
load("@fbcode_macros//build_defs:native_rules.bzl", "buck_command_alias", "buck_genrule")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load(":compile_image_features.bzl", "compile_image_features")
load(":image_source.bzl", "image_source")
load(":image_utils.bzl", "image_utils")
load(":target_tagger.bzl", "image_source_as_target_tagged_dict", "new_target_tagger")

def _add_run_in_subvol_target(name, kind, extra_args = None):
    buck_command_alias(
        name = name + "-" + kind,
        args = ["--layer", "$(location {})".format(":" + name)] + (
            extra_args if extra_args else []
        ),
        exe = "//fs_image:nspawn-run-in-subvol",
        visibility = [],
    )

def _current_target(target_name):
    return target_utils.to_label(
        config.get_current_repo_name(),
        native.package_name(),
        target_name,
    )

def _image_layer_impl(
        _rule_type,
        _layer_name,
        _make_subvol_cmd,
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
        # Set this to emit a `-boot` target, running which will boot
        # `systemd` inside the image.
        enable_boot_target = False,
        visibility = None):
    visibility = get_visibility(visibility, _layer_name)
    if mount_config == None:
        mount_config = {}
    for key in ("build_source", "is_directory"):
        if key in mount_config:
            fail("`{}` cannot be customized".format(key), "mount_config")
    mount_config["is_directory"] = True
    mount_config["build_source"] = {
        # Don't attempt to target-tag this because this would complicate
        # MountItem, which would have to contain `Subvol` and know how to
        # serialize it (P106589820).  This is much messier than the current
        # approach of explicit target & layer lookups in `_BuildSource`.
        "source": _current_target(_layer_name),
        # The compiler knows how to resolve layer locations.  For now, we
        # don't support mounting a subdirectory of a layer because that
        # might make packaging more complicated, but it could be done.
        "type": "layer",
    }

    buck_genrule(
        name = _layer_name,
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
                layer_name_quoted = shell.quote(_layer_name),
                refcounts_dir_quoted = paths.join(
                    "$GEN_DIR",
                    shell.quote(get_project_root_from_gen_dir()),
                    "buck-out/.volume-refcount-hardlinks/",
                ),
                make_subvol_cmd = _make_subvol_cmd,
                # To make layers "image-mountable", provide `mountconfig.json`.
                quoted_mountconfig_json = shell.quote(
                    struct(**mount_config).to_json(),
                ),
            ),
            volume_min_free_bytes = layer_size_bytes,
            rule_type = _rule_type,
            target_name = _layer_name,
        ),
        # Layers are only usable on the same host that built them, so
        # keep our output JSON out of the distributed Buck cache.  See
        # the docs for BuildRule::isCacheable.
        cacheable = False,
        type = _rule_type,  # For queries
        visibility = visibility,
    )
    _add_run_in_subvol_target(_layer_name, "container")
    if enable_boot_target:
        _add_run_in_subvol_target(_layer_name, "boot", extra_args = ["--boot"])

# See the `_image_layer_impl` signature for all other supported kwargs.
def image_layer(
        name,
        # The name of another `image_layer` target, on top of which the
        # current layer will install its features.
        parent_layer = None,
        # List of `image.feature` target paths and/or nameless structs from
        # `image.feature`.
        features = None,
        # A struct containing fields accepted by `_build_opts` from
        # `image_layer_compiled.bzl`.
        build_opts = None,
        **image_layer_kwargs):
    _image_layer_impl(
        _rule_type = "image_layer",
        _layer_name = name,
        # Build a new layer. It may be empty.
        _make_subvol_cmd = compile_image_features(
            current_target = _current_target(name),
            parent_layer = parent_layer,
            features = features,
            build_opts = build_opts,
        ),
        **image_layer_kwargs
    )

# See the `_image_layer_impl` signature for all other supported kwargs.
def image_sendstream_layer(
        name,
        # `image.source` (see `image_source.bzl`) or path to a target
        # outputting a btrfs send-stream of a subvolume.
        source = None,
        # A struct containing fields accepted by `_build_opts` from
        # `image_layer_compiled.bzl`.
        build_opts = None,
        # Future: Support `parent_layer`.  Mechanistically, applying a
        # send-stream on top of an existing layer is just a regular `btrfs
        # receive`.  However, the rules in the current `receive`
        # implementation for matching the parent to the stream are kind of
        # awkward, and it's not clear whether they are right for us in Buck.
        **image_layer_kwargs):
    target_tagger = new_target_tagger()
    _image_layer_impl(
        _rule_type = "image_sendstream_layer",
        _layer_name = name,
        _make_subvol_cmd = compile_image_features(
            current_target = _current_target(name),
            parent_layer = None,
            features = [struct(
                items = struct(
                    receive_sendstreams = [{
                        "source": image_source_as_target_tagged_dict(
                            target_tagger,
                            source,
                        ),
                    }],
                ),
                deps = target_tagger.targets.keys(),
            )],
            build_opts = build_opts,
        ),
        **image_layer_kwargs
    )
