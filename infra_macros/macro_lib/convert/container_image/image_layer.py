#!/usr/bin/env python2
'''
An `image_layer` is an `image_feature` with some additional parameters.  Its
purpose to materialize that `image_feature` as a btrfs subvolume in the
per-repo `buck-image/out/volume/targets`.

We call the subvolume a "layer" because it can be built on top of a
snapshot of its `parent_layer`, and thus can be represented as a `btrfs
send`-style diff for more efficient storage & distribution.

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
'''
import collections
import os

from pipes import quote


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


base = import_macro_lib('convert/base')
Rule = import_macro_lib('rule').Rule
image_feature = import_macro_lib('convert/container_image/image_feature')


class ImageLayerConverter(base.Converter):
    'Start by reading the module docstring.'

    def get_fbconfig_rule_type(self):
        return 'image_layer'

    def convert(
        self,
        base_path,
        name=None,
        # The name of another `image_layer` target, on top of which the
        # current layer will install its features.
        parent_layer=None,
        # Future: should we determine this dynamically from the installed
        # artifacts (by totaling up the bytes needed for copied files, RPMs,
        # tarballs, etc)?  NB: At the moment, this number doesn't work
        # precisely as a user would want -- we just require that the base
        # volume have at least this much space, -- but hopefully people
        # don't have to change it too much.
        layer_size_bytes=10e10,
        visibility=None,
        **image_feature_kwargs
    ):
        # For ease of use, a layer takes all the arguments of a feature, so
        # just make an implicit feature target to implement this.
        feature_name = name + '-feature'
        feature_target = \
            ':' + feature_name + image_feature.DO_NOT_DEPEND_ON_FEATURES_SUFFIX
        rules = image_feature.ImageFeatureConverter(self._context).convert(
            base_path,
            name=feature_name,
            **image_feature_kwargs
        )

        parent_layer_feature_query = '''
            attrfilter(type, image_feature, deps({}))
        '''.format(parent_layer)

        # We will ask Buck to ensure that the outputs of the direct
        # dependencies of our `image_feature`s are available on local disk.
        # See `Implementation notes: Dependency resolution` in `__doc__`.
        this_layer_feature_query = '''
            attrfilter(type, image_feature, deps({my_feature}))
                {minus_parent_features}
        '''.format(
            my_feature=feature_target,
            minus_parent_features=(' - ' + parent_layer_feature_query)
                if parent_layer else '',
        )

        rules.append(Rule('genrule', collections.OrderedDict(
            name=name,
            out=name + '.json',
            type=self.get_fbconfig_rule_type(),  # For queries
            # Layers are only usable on the same host that built them, so
            # keep our output JSON out of the distributed Buck cache.  See
            # the docs for BuildRule::isCacheable.
            cacheable=False,
            bash='''
            # CAREFUL: To avoid inadvertently masking errors, we should
            # only perform command substitutions with variable
            # assignments.
            set -ue -o pipefail

            binary_path=$(location {helper_base}:artifacts-dir)
            # Common sense would tell us to find helper programs via:
            #   os.path.dirname(os.path.abspath(__file__))
            # The benefit of using \\$(location) is that it does not bake
            # an absolute paths into our command.  This **should** help
            # the cache continue working even if the user moves the repo.
            artifacts_dir=\\$( "$binary_path" )

            # Future-proofing: keep all Buck target subvolumes under
            # "targets/" in the per-repo volume, so that we can easily
            # add other types of subvolumes in the future.
            binary_path=$(location {helper_base}:volume-for-repo)
            volume_dir=\\$("$binary_path" "$artifacts_dir" {min_free_bytes})
            subvolumes_dir="$volume_dir/targets"
            mkdir -m 0700 -p "$subvolumes_dir"

            # Capture output to a tempfile to hide logspam on successful runs.
            my_log=`mktemp`

            log_on_error() {{
              exit_code="$?"
              # Always persist the log for debugging purposes.
              collected_logs="$artifacts_dir/image_layer.log"
              (
                  date
                  cat "$my_log" || :
              ) |& flock "$collected_logs" tee -a "$collected_logs"
              # If we had an error, also dump the log to stderr.
              if [[ "$exit_code" != 0 ]] ; then
                cat "$my_log" 1>&2
              fi
              rm "$my_log"
            }}
            # Careful: do NOT replace this with (...) || (...), it will lead
            # to `set -e` not working as you expect, because bash is awful.
            trap log_on_error EXIT

            (
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
              binary_path=$(location {helper_base}:subvolume-version)
              subvolume_ver=\\$( "$binary_path" )
              subvolume_wrapper_dir={subvolume_name_quoted}":$subvolume_ver"

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
              $(location {helper_base}:subvolume-garbage-collector) \
                --refcounts-dir "$refcounts_dir" \
                --subvolumes-dir "$subvolumes_dir" \
                --new-subvolume-wrapper-dir "$subvolume_wrapper_dir" \
                --new-subvolume-json "$OUT"

              # Take note of `targets_and_outputs` below -- this enables the
              # compiler to map the `__BUCK_TARGET`s in the outputs of
              # `image_feature` to those targets' outputs.
              $(location {helper_base}:compiler) \
                --subvolumes-dir "$subvolumes_dir" \
                --subvolume-rel-path \
                  "$subvolume_wrapper_dir/"{subvolume_name_quoted} \
                --parent-layer-json {parent_layer_json_quoted} \
                --child-layer-target {current_target_quoted} \
                --child-feature-json $(location {my_feature_target}) \
                --child-dependencies \
                  $(query_targets_and_outputs 'deps({my_deps_query}, 1)') \
                    > "$OUT"

              # Our hardlink-based refcounting scheme, as well as the fact
              # that we keep subvolumes in a special location, make it a
              # terrible idea to mutate the output after creation.
              chmod a-w "$OUT"
            ) &> "$my_log"
            '''.format(
                min_free_bytes=int(layer_size_bytes),
                helper_base='//tools/build/buck/infra_macros/macro_lib/'
                    'convert/container_image',
                parent_layer_json_quoted='$(location {})'.format(parent_layer)
                    if parent_layer else "''",
                subvolume_name_quoted=quote(name),
                current_target_quoted=quote(self.get_target(
                    self._context.config.get_current_repo_name(),
                    base_path,
                    name,
                )),
                my_feature_target=feature_target,
                my_deps_query=this_layer_feature_query,
                refcounts_dir_quoted=os.path.join(
                    '$GEN_DIR',
                    quote(self.get_fbcode_dir_from_gen_dir()),
                    'buck-out/.volume-refcount-hardlinks/',
                ),
            ),
            visibility=visibility,
        )))

        return rules
