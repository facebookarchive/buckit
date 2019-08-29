#!/usr/bin/env python2
"""
DO NOT DEPEND ON THIS TARGET DIRECTLY, except through the `features=` field
of `image_feature` or `image_layer`.  A direct dependency will not work the
way you expect, and you will end up with incorrect behavior.

## Composing images using `image_feature`

When building regular binaries, one will often link multiple independent
libraries that know nothing about one another. Each of those libraries
may depend on other libraries, and so forth.

This ability to **compose** largely uncoupled pieces of functionality is
an essential tool of a software engineer.

`image_feature` is a way of bringing the same sort of compositionality to
building filesystem images.

A feature specifies a set of **items**, each of which describes some aspect
**of a desired end state** for the filesystem.  Examples:
 - A directory must exist.
 - A taraball must be extracted at this location.
 - An RPM must be installed, or must be **ABSENT** from the filesystem.
 - Other `image_feature` that must be installed.

Importantly, the specifications of an `image_feature` are not ordered. They
are not commands or instructions.  Rather, they are a declaration of what
should be true. You can think of a feature as a thunk or callback.

In order to convert the declaration into action, one makes an `image_layer`.
Read that target's docblock for more info, but in essence, that will:
 - specify the initial state of the filesystem (aka the parent layer)
 - verify that the features can be applied correctly -- that dependencies
   are satisfied, that no features provide duplicate paths, etc.
 - install the features in dependency order,
 - capture the resulting filesystem, ready to be used as another parent layer.
"""

load("@bazel_skylib//lib:shell.bzl", "shell")
load("@bazel_skylib//lib:types.bzl", "types")
load("@fbcode_macros//build_defs:native_rules.bzl", "buck_genrule")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load(":crc32.bzl", "hex_crc32")
load(":target_tagger.bzl", "extract_tagged_target", "image_source_as_target_tagged_dict", "new_target_tagger", "normalize_target", "tag_required_target_key", "tag_target", "target_tagger_to_feature")
load(":wrap_runtime_deps.bzl", "maybe_wrap_runtime_deps_as_build_time_deps")

# ## Why are `image_feature`s forbidden as dependencies?
#
# The long target suffix below exists to discourage people from directly
# depending on `image_feature`s.  They are not real targets, but rather a
# language feature to make it easy to compose independent features of
# container images.
#
# A normal Buck target is supposed to produce an output that completely
# encapsulates the outputs of all of its dependencies (think static
# linking), so in deciding whether to build a file or use a cached output,
# Buck will only consider direct dependencies, not transitive ones.
#
# In contrast, `image_feature` simply serializes its keyword arguments to
# JSON.  It does not consume the outputs of its dependencies -- it reads
# neither regular target outputs, nor the JSONs of the `image_feature`s, on
# which it depends.
#
# By violating Buck semantics, `image_features` creates two problems for
# targets that might depend on them:
#
# 1) Buck will build any target depending on an `image_feature` immediately
#    upon ensuring that its JSON output exists in the output tree.  It is
#    possible that the output tree lacks, or contains stale versions of, the
#    outputs of the targets, on which the `image_feature` itself depends.
#
# 2) If the output of a dependency of an `image_feature` changes, this will
#    cause the feature to rebuild.  However, the output of the `image_feature`
#    will remain unchanged, and so any target depending on the `image_feature`
#    will **NOT** get rebuilt.
#
# For these reasons, special logic is required to correctly depend on
# `image_feature` targets.  At the moment, we are not aware of any reason to
# have direct access to the `image_feature` JSON outputs in any case.  Most
# users will want to depend on build artifacts that are downstream of
# `image_feature`, like `image_layer`.
#
# Maintainers of this code: please change this string at will, **without**
# searching the codebase for people who might be referring to it.  They have
# seen this blob, and they have agreed to have their code broken without
# warning.  Do not incentivize hacky engineering practices by "being nice."
# (Caveat: don't change it daily to avoid forcing excessive rebuilds.)
DO_NOT_DEPEND_ON_FEATURES_SUFFIX = (
    "_IF_YOU_REFER_TO_THIS_RULE_YOUR_DEPENDENCIES_WILL_BE_BROKEN_" +
    "SO_DO_NOT_DO_THIS_EVER_PLEASE_KTHXBAI"
)

def _coerce_dict_to_items(maybe_dct):
    "Any collection that takes a list of pairs also takes a dict."
    return maybe_dct.items() if types.is_dict(maybe_dct) else maybe_dct

def _normalize_stat_options(d):
    if "user:group" in d:
        # enriched namedtuples cannot deal with colons in names
        d["user_group"] = d.pop("user:group")
    return d

def _normalize_make_dirs(make_dirs):
    if make_dirs == None:
        return []

    normalized = []
    for d in _coerce_dict_to_items(make_dirs):
        if types.is_string(d):
            d = {"into_dir": "/", "path_to_make": d}
        elif types.is_tuple(d):
            if len(d) != 2:
                fail(
                    "make_dirs tuples must have the form: " +
                    "(working_dir, dirs_to_create)",
                )
            d = {"into_dir": d[0], "path_to_make": d[1]}
        normalized.append(_normalize_stat_options(d))
    return normalized

def _normalize_mounts(target_tagger, mounts):
    if mounts == None:
        return []

    normalized = []
    for mnt in _coerce_dict_to_items(mounts):
        dct = {"mount_config": None, "mountpoint": None, "target": None}
        source = None
        if types.is_tuple(mnt):
            if len(mnt) != 2:
                fail((
                    "`mounts` item {} must be " +
                    "(mountpoint, target OR dict)"
                ).format(mnt))
            dct["mountpoint"] = mnt[0]
            source = mnt[1]
        else:
            source = mnt

        if types.is_string(source):
            dct["target"] = source
            tag_required_target_key(target_tagger, dct, "target")
        elif types.is_dict(source):
            # At present, we only accept dicts that carry an inline mount
            # config (identical to the `mountconfig.json` of a mountable
            # target, but without the overhead of having an on-disk target
            # output). These two equivalent examples illustrate the usage:
            #
            #     mounts = {"/path/to": image.host_dir_mount(
            #         source = "/home/banana/rama",
            #     )}
            #
            #     mounts = [image.host_dir_mount(
            #         mountpoint = "/path/to",
            #         source = "/home/banana/rama",
            #     )]
            #
            # In the future, we might accept other keys here, e.g. to
            # override mount options or similar.
            if sorted(list(source.keys())) != ["mount_config"]:
                fail("bad keys in `mounts` item {}".format(mnt))
            dct["mount_config"] = source["mount_config"]
        else:
            fail("`mounts` item {} lacks a mount source".format(mnt))

        normalized.append(dct)

    return normalized

def _maybe_wrap_executable_target(target_tagger, target, wrap_prefix, **kwargs):
    # The target to wrap may be in a different directory, so we normalize
    # its path to ensure the hashing is deterministic.  This assures reuse
    # at least within the current TARGETS files.
    target = normalize_target(target)

    # The wrapper target is plumbing, so it will start with the provided
    # prefix to hide it from e.g.  tab-completion.  Then, it includes an
    # excerpt of the original target name to ease debugging.  Lastly, a hash
    # of the full target path accounts for identically-named targets from
    # different directories.
    _, name = target.split(":")
    wrapped_target = wrap_prefix + "__" + (
        name if len(name) < 15 else (name[:6] + "..." + name[-6:])
    ) + "__" + hex_crc32(target)

    # The `wrap_runtime_deps_as_build_time_deps` docblock explains this:
    was_wrapped, maybe_target = maybe_wrap_runtime_deps_as_build_time_deps(
        name = wrapped_target,
        target = target,
        **kwargs
    )
    return was_wrapped, tag_target(target_tagger, maybe_target)

def _normalize_install_files(target_tagger, files, visibility, is_executable):
    if files == None:
        return []

    normalized = []
    kwarg_name = "install_executables" if is_executable else "install_data"

    for d in _coerce_dict_to_items(files):
        if types.is_tuple(d):
            if len(d) != 2:
                fail(
                    "`{}` tuples must have the form: ".format(kwarg_name) +
                    "(target_to_copy, destination_path)",
                )
            if types.is_string(d[1]):
                d = {"dest": d[1], "source": d[0]}
            elif types.is_dict(d[1]):
                rest_of_d = d[1]
                if "source" in rest_of_d:
                    fail('"source": {...} must not set source in the dict')
                d = {"source": d[0]}
                d.update(rest_of_d)
            else:
                fail("Tuple element in `{}` has unexpected type: {}".format(
                    kwarg_name,
                    d[1],
                ))
        d["is_executable_"] = is_executable  # Changes default permissions

        # Normalize to the `image.source` interface
        src = image_source_as_target_tagged_dict(target_tagger, d.pop("source"))

        # NB: We don't have to wrap executables because they already come
        # from a layer, which would have wrapped them if needed.
        #
        # Future: If `is_executable` is not set, we might use a Buck macro
        # that enforces that the target is non-executable, as I suggested on
        # Q15839.  This should probably go in `tag_required_target_key` to
        # ensure that we avoid "unwrapped executable" bugs everywhere.  A
        # possible reason NOT to do this is that it would require fixes to
        # `install_data` invocations that extract non-executable contents
        # out of a directory target that is executable.
        if is_executable and src["source"]:
            was_wrapped, src["source"] = _maybe_wrap_executable_target(
                target_tagger = target_tagger,
                # Peel back target tagging since this helper expects untagged.
                target = extract_tagged_target(src.pop("source")),
                wrap_prefix = "install_executables_wrap_source",
                visibility = visibility,
                # NB: Buck makes it hard to execute something out of an
                # output that is a directory, but it is possible so long as
                # the rule outputting the directory is marked executable
                # (see e.g. `print-ok-too` in `feature_install_files`).
                path_in_output = src.get("path", None),
            )
            if was_wrapped:
                # The wrapper above has resolved `src["path"]`, so the
                # compiler does not have to.
                src["path"] = None

        d["source"] = src
        normalized.append(_normalize_stat_options(d))
    return normalized

def _normalize_tarballs(target_tagger, tarballs, visibility):
    if tarballs == None:
        return []

    normalized = []
    for d in _coerce_dict_to_items(tarballs):
        if not types.is_dict(d):
            fail("`tarballs` must contain only dicts")

        # Skylark linters crash on seeing the XOR operator :/
        if (("generator" in d) + ("tarball" in d)) != 1:
            fail("Exactly one of `generator`, `tarball` must be set")
        if "generator_args" in d and "generator" not in d:
            fail("Got `generator_args` without `generator`")

        if "tarball" in d:
            tag_required_target_key(target_tagger, d, "tarball")
        else:
            _was_wrapped, d["generator"] = _maybe_wrap_executable_target(
                target_tagger = target_tagger,
                target = d.pop("generator"),
                wrap_prefix = "tarball_wrap_generator",
                visibility = visibility,
            )

        if "hash" not in d:
            fail(
                "To ensure that tarballs are repo-hermetic, you must pass " +
                '`hash = "algorithm:hexdigest"` (checked via Python hashlib)',
            )

        d.setdefault("generator_args", [])
        d.setdefault("force_root_ownership", False)

        normalized.append(d)
    return normalized

def _normalize_remove_paths(remove_paths):
    if remove_paths == None:
        return []

    normalized = []
    required_keys = sorted(["action", "path"])
    valid_actions = ("assert_exists", "if_exists")
    for path in _coerce_dict_to_items(remove_paths):
        if types.is_dict(path):
            if required_keys != sorted(path.keys()):
                fail("remove_paths {} must have keys {}".format(
                    path,
                    required_keys,
                ))
            dct = path
        elif types.is_tuple(path):
            if len(path) != 2:
                fail("remove_paths item {} must be (path, action)".format(path))
            dct = {"action": path[1], "path": path[0]}
        else:
            if not types.is_string(path):
                fail("`remove_paths` item must be string, not {}".format(path))
            dct = {"action": "assert_exists", "path": path}
        if dct["action"] not in valid_actions:
            fail("Action for remove_paths {} must be in {}".format(
                path,
                valid_actions,
            ))
        normalized.append(dct)

    return normalized

def _rpm_name_or_source(name_source):
    # Normal RPM names cannot have a colon, whereas target paths
    # ALWAYS have a colon. `image.source` is a struct.
    if ":" in name_source or not types.is_string(name_source):
        return "source"
    else:
        return "name"

def _normalize_rpms(target_tagger, rpms):
    if rpms == None:
        return []

    normalized = []
    required_keys = sorted(["name", "action"])
    valid_actions = ("install", "remove_if_exists")
    for rpm in _coerce_dict_to_items(rpms):
        if types.is_dict(rpm):
            if required_keys != sorted(rpm.keys()):
                fail("Rpm {} must have keys {}".format(rpm, required_keys))
            dct = rpm
        elif types.is_tuple(rpm):  # Handles `rpms` being a dict, too
            if len(rpm) != 2:
                fail("Rpm entry {} must be (name, action)".format(rpm))
            dct = {"action": rpm[1], _rpm_name_or_source(rpm[0]): rpm[0]}
        else:
            if not types.is_string(rpm):
                fail("Bad rpms item {}".format(rpm))
            dct = {"action": "install", _rpm_name_or_source(rpm): rpm}

        if dct["action"] not in valid_actions:
            fail("Action for rpm {} must be in {}".format(rpm, valid_actions))

        source = dct.pop("source", None)
        if source != None:
            dct["source"] = image_source_as_target_tagged_dict(
                target_tagger,
                source,
            )

        normalized.append(dct)
    return normalized

def _normalize_symlinks(symlinks):
    if symlinks == None:
        return []

    normalized = []
    for d in _coerce_dict_to_items(symlinks):
        if types.is_tuple(d):
            if len(d) != 2:
                fail(
                    "symlink tuples must have the form: " +
                    "(symlink_source, symlink_dest)",
                )
            d = {"dest": d[1], "source": d[0]}
        normalized.append(d)
    return normalized

def image_feature(
        name = None,
        # An iterable of directories to make in the image --
        #  - `into_dir` is a image-absolute path, inside which
        #    we should create more directories. It must be created by
        #    another `image_feature` item.
        #  - `path_to_make` is a path relative to `into_dir`, which will be
        #    created.
        # Order is not significant, the image compiler will sort the actions
        # automatically.  Supported formats for the items:
        #  - string: 'image_absolute/path/to/make'
        #  - tuple: ('into/image_absolute/dir', 'path/to/make')
        #  - dict: {'into_dir': '...', 'path_to_make': '...'}
        make_dirs = None,
        # An iterable or dictionary of targets that provide in-container
        # mounts of subtrees or files.  Two* syntax variants are allowed:
        #
        #    # Implies the target-specified "conventional" mount-point.
        #    mounts = [
        #        "//path/to:name_of_mount",
        #        "//path/to:another_mount_name",
        #    ],
        #
        #    # Explicit mount-points, overriding whatever the target
        #    # recommends as the default.
        #    mounts = {
        #        "/mount/point": "//path/to:name_of_mount",
        #        "/mount/point": "//path/to:name_of_mount",
        #    }
        #
        # Shadowing mountpoints will never be allowed. Additionally, for now:
        #
        #   - The mountpoint must not exist, and is automatically created as
        #     an empty directory or file with root:root ownership.  If
        #     needed, we may add a flag to accept pre-existing empty
        #     mountpoints (`remove_paths` is a workaround).  The motivation
        #     for auto-creating the mountpoint is two-fold:
        #       * This reduces boilerplate in features with `mounts` -- the
        #         properties of the mountpoint don't matter.
        #       * This guarantees the mounpoint is empty.
        #
        #   - Nesting mountpoints is forbidden. If support is ever added,
        #     we should make the intent to nest very explicit (syntax TBD).
        #
        #   - All mounts are read-only.
        #
        # A mount target, roughly, is a JSON blob with a "type" string, a
        # "source" location interpretable by that type, and a
        # "default_mountpoint".  We use targets as mount sources because:
        #
        #   - This allows mounts to be materialized, flexibly, at build-time,
        #     and allows us to provide a cheap "development time" proxy for
        #     mounts that might be distributed in a more costly way at
        #     deployment time.
        #
        #   - This allows us Buck to cleanly cache mounts fetched from
        #     package distribution systems -- i.e.  we can use the local
        #     Buck cache the same way that Docker caches downloaded images.
        #
        # Adding a mount has two side effects on the `image.layer`:
        #   - The mount will be materialized in the `buck-image-out` cache
        #     of the local repo, so your filesystem acts as WYSIWIG.
        #   - The mount will be recorded in `/meta/private/mount`.  PLEASE,
        #     do not rely on this serializaation format for now, it will
        #     change.  That's why it's "private".
        #
        # * There is actually a third syntax that is accepted in order to
        #   support helper functions for declaring mounts -- see
        #   `_image_host_mount` for an example.
        #
        # Future: we may need another feature for removing mounts provided
        # by parent layers.
        mounts = None,
        # The `install_` arguments are used to copy Buck build artifacts
        # (wholly or partially) into an image. Basic syntax:
        #
        # Each argument is an iterable of targets to copy into the image.
        # Files to copy can be specified using `image.source` (use this to
        # grab one file from a directory or layer output, docs in
        # `image_source.bzl`), or as string target paths.  You can supply a
        # list mixing dicts and 2-element tuples (as below), or a dict keyed
        # by source target (more below).
        #
        # Prefer to use the shortest form possible, instead of repeating the
        # defaults in your spec.
        #
        # If you are supplying a list, here is what it can contain:
        #   - tuple: ('//source/to:copy', 'image_absolute/dest/filename')
        #   - dict: {
        #         # An image-absolute path, including a filename for the
        #         # file being copied.  The directory of `dest` must get
        #         # created by another `image_feature` item.
        #         'dest': 'image_absolute/dir/filename',
        #
        #         # The Buck target to copy (or to copy from).
        #         'source': '//target/to/copy',  # Or an `image.source()`
        #
        #         # Please do NOT copy these defaults into your TARGETS:
        #         'user:group': 'root:root',
        #         'mode': 'a+r',  # or 'a+rx' for `install_executables`
        #     }
        #
        # If your iterable is a dict, you can use items of two types:
        #   - `'//source/to:copy': 'image/dest',`
        #   - `'//source/to:copy': { ... dict as above, minus `source` ... },`
        #
        # The iterable's order is not signficant, the image compiler will
        # sort the actions automatically.
        #
        # If the file being copied is an executable (e.g. `cpp_binary`,
        # `python_binary`), use `install_executable`.  Ditto for copying
        # executable files from inside directories output by other (custom?)
        # executable rules. For everything else, use `install_data` [1].
        #
        # The implementation of `install_executables` differs significantly
        # in `@mode/dev` in order to support the execution of in-place
        # binaries (dynamically linked C++, linktree Python) from within an
        # image.  Internal implementation differences aside, the resulting
        # image should "quack" like your real, production `@mode/opt`.
        #
        # [1] Corner case: if you want to copy a non-executable file from
        # inside a directory output by a Buck target, which is marked
        # executable, then you should use `install_data`, even though the
        # underlying rule is executable.
        #
        # Design note: This API forces you to distinguish between source
        # targets that are executable and those that are not, because (until
        # Buck supports providers), it is not possible to deduce this
        # automatically at parse-time.
        install_data = None,
        install_executables = None,
        # An iterable of tarballs to extract inside the image.
        #
        # Each item must specify EXACTLY ONE of `tarball`, `generator`:
        #
        #   - EITHER: `tarball`, a Buck target that outputs a tarball.  You
        #     might consider `export_file` or `genrule`.
        #
        #   - OR: `generator`, a path to an executable target, which
        #     will run every time the layer is built.  It is supposed to
        #     generate a deterministic tarball.  The script's contract is:
        #       * Its arguments are the strings from `generator_args`,
        #         followed by one last argument that is a path to an
        #         `image.layer`-provided temporary directory, into which the
        #         generator must write its tarball.
        #       * The generator must print the filename of the tarball,
        #         followed by a single newline, to stdout.  The filename
        #         MUST be relative to the provided temporary directory.
        #
        # In deciding between `tarball` and `generator*`, you are trading
        # off disk space in the Buck cache for the resources (e.g. latency,
        # CPU usage, or network usage) needed to re-generate the tarball.
        # For example, using `generator*` is a good choice when it simply
        # performs a download from a fast immutable blob store.
        #
        # Note that a single script can potentially be used both as a
        # generator, and to produce cached artifacts, see how the compiler
        # test `TARGETS` uses `hello_world_tar_generator.sh` in a genrule.
        #
        # Additionally, every item must contain these keys:
        #   - `hash`, of the format `<python hashlib algo>:<hex digest>`,
        #     which is the hash of the content of the tarball before any
        #     decompression or unpacking.
        #   - `into_dir`, the destination of the unpacked tarball in the
        #     image.  This is an image-absolute path to a directory that
        #     must be created by another `image_feature` item.
        #
        # As with other `image.feature` items, order is not signficant, the
        # image compiler will sort the items automatically.  Tarball items
        # must be dicts -- example:
        #     {
        #         'hash': 'sha256:deadbeef...',
        #         'into_dir': 'image_absolute/dir',
        #         'tarball': '//target/to:extract',
        #     }
        tarballs = None,
        # An iterable of paths to files or directories to (recursively)
        # remove from the layer.  These are allowed to remove paths
        # inherited from the parent layer, or those installed by RPMs even
        # in this layer.  However, removing other items explicitly added by
        # the current layer is currently not supported since that seems like
        # a design smell -- you should probably refactor the constituent
        # `image.feature`s not to conflict with each other.
        #
        # By default, it is an error if the specified paths are missing from
        # the image.  This form is also supported:
        #     [('/path/to/remove', 'assert_exists|if_exists')],
        # which allows you to explicitly ignore missing paths.
        remove_paths = None,
        # An iterable of RPM package names to install, **without** version
        # or release numbers.  Order is not significant.  Also supported:
        # {'package-name': 'install|remove_if_exists'}.  Note that removals
        # may only be applied against the parent layer -- if your current
        # layer includes features both removing and installing the same
        # package, this will cause a build failure.
        #
        # You may also install an RPM that is the outputs of another buck
        # rule by replacing `package-name` by an `image.source` (docs in
        # `image_source.bzl`), or by a target path.
        rpms = None,
        # An iterable of symlinks to make in the image.  Directories and files
        # are supported independently to provide explicit handling of each
        # source type.  For both `symlinks_to_dirs` and `symlinks_to_files` the
        # following is true:
        #  - `source` is the source file/dir of the symlink.  This file must
        #     exist as we do not support dangling symlinks.
        #  - `dest` is an image-absolute path.  We follow the `rsync`
        #     convention -- if `dest` ends with a slash, the copy will be at
        #     `dest/output filename of source`.  Otherwise, `dest` is a full
        #     path, including a new filename for the target's output.  The
        #     directory of `dest` must get created by another
        #     `image_feature` item.
        symlinks_to_dirs = None,
        symlinks_to_files = None,
        # Iterable of `image_feature` targets that are included by this one.
        # Order is not significant.
        features = None,
        visibility = None):
    """Does not make a layer, simply records what needs to be done. A thunk."""

    # (1) Normalizes & annotates Buck target names so that they can be
    #     automatically enumerated from our JSON output.
    # (2) Builds a list of targets so that this converter can tell Buck
    #     that the `image_feature` depends on it.
    target_tagger = new_target_tagger()

    feature = target_tagger_to_feature(
        target_tagger,
        items = struct(
            # For named features, omit the ugly suffix here since this is
            # meant only for humans to read while debugging.  For inline
            # targets, `image_layer.bzl` sets this to the layer target path.
            target = normalize_target(":" + name) if name else None,
            make_dirs = _normalize_make_dirs(make_dirs),
            install_files = _normalize_install_files(
                target_tagger = target_tagger,
                files = install_data,
                visibility = visibility,
                is_executable = False,
            ) + _normalize_install_files(
                target_tagger = target_tagger,
                files = install_executables,
                visibility = visibility,
                is_executable = True,
            ),
            mounts = _normalize_mounts(target_tagger, mounts),
            tarballs = _normalize_tarballs(target_tagger, tarballs, visibility),
            remove_paths = _normalize_remove_paths(remove_paths),
            # It'd be a bit expensive to do any kind of validation of RPM
            # names right here, since we'd need the repo snapshot to decide
            # whether the names are valid, and whether they contain a
            # version or release number.  That'll happen later in the build.
            rpms = _normalize_rpms(target_tagger, rpms),
            symlinks_to_dirs = _normalize_symlinks(symlinks_to_dirs),
            symlinks_to_files = _normalize_symlinks(symlinks_to_files),
            features = [
                tag_target(target_tagger, f + DO_NOT_DEPEND_ON_FEATURES_SUFFIX)
                for f in features
            ] if features else [],
        ),
        # We need to tell Buck that we depend on these targets, so
        # that `image_layer` can use `deps()` to discover its
        # transitive dependencies.
        #
        # This is a little hacky, because we are forcing these
        # targets to be built or fetched from cache even though we
        # don't actually use them until a later build step --- which
        # might be on a different host.
        #
        # Future: Talk with the Buck team to see if we can eliminate
        # this inefficiency.
        #
        # To understand the self-dependency, see the `fake_macro_library` doc.
        extra_deps = ["//fs_image/buck:image_feature"],
    )

    # Anonymous features do not emit a target, but can be used inline as
    # part of an `image.layer`.
    if not name:
        return feature

    # Serialize the arguments and defer our computation until build-time.
    # This allows us to automatically infer what is provided by RPMs & TARs,
    # and makes the implementation easier.
    #
    # Caveat: if the serialization exceeds the kernel's MAX_ARG_STRLEN,
    # this will fail (128KB on the Linux system I checked).
    #
    # TODO: Print friendlier error messages on user error.
    buck_genrule(
        # The constant declaration explains the reason for the name change.
        name = name + DO_NOT_DEPEND_ON_FEATURES_SUFFIX,
        out = name + ".json",
        type = "image_feature",  # For queries
        cmd = 'echo {deps} > /dev/null; echo {out} > "$OUT"'.format(
            deps = " ".join([
                "$(location {})".format(t)
                for t in sorted(feature.deps)
            ]),
            out = shell.quote(feature.items.to_json()),
        ),
        visibility = get_visibility(visibility, name),
    )

    # NB: it would be easy to return the path to the new feature target
    # here, enabling the use of named features inside `features` lists of
    # layers, but this seems like an unreadable pattern, so instead:
    return None
