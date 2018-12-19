load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def fbpkg_builder(
        name,
        path_actions = None,
        # We have to have a default here because of our call to `fbpkg expire`
        expire_seconds_from_now = 86400,  # Contbuild's current sitevar default
        allow_nonportable_artifacts = False,
        visibility = None):
    """
    `buck run` this target to build a new version of the named package,
    comprised of the build artifacts and symlinks specified by
    `path_actions` (described below).


    ## IMPORTANT

      - If your package has a configuration in Configerator, it is IGNORED
        by this build rule.  This is intentional -- this target is meant to
        replace Configerator for certain fbcode-centric uses of fbpkgs.

      - The semantics differ from `fbpkg build` in some key ways, see below.


    ## Usage

    Note that `buck build` does NOT create a new fbpkg version, but only
    builds its contents (locally), and writes a script that knows how to
    publish a new fbpkg version.  To publish:

    `buck run @mode/opt //path/to:your_fbpkg_name` OR
    `buck run @mode/opt //path/to:your_fbpkg_name -- --json`

    This prints to stdout `your_fbpkg_name:uuid` or the `fbpkg build` JSON
    summary for the built package.


    ## Arguments

    `name`: The name of the rule AND the name of the fbpkg.  IMPORTANT: This
    invariant must never change, because it is very useful to be able to
    reliably infer the fbpkg name from the target path.  For example,
    `SandcastleGetContbuildForPackageTrait` relies on this.

    `path_actions`: A map of the form `{'path/in/pkg': (ACTION, SOURCE)}`.
    ACTION can either be `copy`, in which case SOURCE is a target path, or
    `symlink`, in which case SOURCE is `another/path/in/pkg`. Example:
        path_actions = {
           'widgets/bar': ('copy', '//foo:bar'),
           'widgets/foo': ('copy', ':foo'),
           'links/foo': ('symlink', 'widgets/foo'),
        }

    `expire_seconds_from_now`: Try to ensure that the built package expires
    no earlier than this.  This may fail is we race with the deletion of a
    pre-existing copy of this exact package, or if the maximum package
    lifetime is reached (search for T38118278 in this code).

    `allow_nonportable_artifacts`: Most people should NEVER use this.  If
    you try to `buck run` from @mode/dev, you will get an explanation of
    when this might be appropriate.

    `visibility`: The visibility of this rule, modified by `visibility.bzl`.


    ## Important differences from `fbpkg build`

      - Until T38118278 is fixed, `fbpkg build` can end up making a
        package that is bitwise-identical to a pre-existing one.  Here, in
        `fbpkg_builder`, this is not an error -- we just return the
        identification of the existing package.  IMPORTANT: you must not
        rely on fbpkg content deduplication -- for one, it's slated to go
        away.  For two, in this `fbpkg_build` implementation, symlinks are
        marked with the creation time of the `buck run`, which alone
        ensures a new fbpkg version.

      - We will try extend the lifetime of a pre-existing bitwise-identical
        version so that it is no less than our `expire_seconds_from_now`.
        This works up to the hardcoded maximum lifetime of the version --
        i.e. at present, normal ephemerals can exist no more than 4 weeks.

      - Some options are not available.  Read the sections `Future non-work`
        and `Future work` to see if an option can be supported.

      - Instead of printing `package_name:short_uuid`, this always prints
        the full UUID.  The reason is that I've seen fbpkg users create
        short all-hex tags, which would be ambiguous with shortened UUIDs.


    ## Design rationale

    The goal is to expose the subset of fbpkg features that is safe to use
    for fbcode developer & CI/CD builds (devserver, diffs, and contbuild).

    Q:  Why should I use this instead of `fbpkg build` from traditional
        Configerator BuildConfigs?
    A:  You don't have to use this, but some benefits include:
          - Developer efficiency: Adding a new file to your service?  You
            only need one diff in one repo.
          - Determinism: Everything about your fbpkg version is determined
            by an fbsource hash (caveat: `fbpkg meta` is globally mutable),

    Q:  Why do I need to `buck run`, couldn't `buck build` build the fbpkg?
    A:  Although fbpkgs are immutable byte strings, and thus could make
        sense as true build artifacts, there are a number of complications
        that make this undesirable:
          - Buck refuses to provide a notion of an "expirable" artifact, so
            making fbpkgs be build artifacts would make builds be fragile due
            to package expiration.  Discussion:
            fb.facebook.com/groups/askbuck/permalink/2228528467195756/
          - Demand control: It may place undue stress on fbpkg to have a 1:1
            correspondence between a `buck build foo/...` and the publication
            of a bunch of new ephemerals.
          - `fpbkg`s must not be built from `@mode/dev`, but to enforce this
            at build-time would mean breaking `buck build dir/...`. See
            @markisaa's comments on this discussion:
            fb.facebook.com/groups/fbcode.foundation/permalink/1522831957819271

    Q:  Why don't you expose all `fbpkg build` / `BuildConfig` options
        directly and transparently?
    A:  This rule is meant for the purposes of CI/CD (and associated
        development), so there is a single "straight and narrow" path,
        including core constraints like (implications after the dash):
          - The output package must be entirely determined by `buck build`
            -- so none of the "extra command" options are supported.
          - Only ephemerals are supported, since this is NOT a release
            mechanism -- thus, our preferred way of addressing packages is
            via full-length UUID.
          - This is a "plumbing" command -- so we use `--yes` to avoid prompts.
          - We must handle duplicate packages the same as new ones, because
            we lack a robust way of preventing duplicate packages, and
            because supporting `pre_compressed` is an explicit goal -- we
            therefore call `fbpkg build` with `--silent-duplicate-error`,
            and follow it with an `fbpkg expire`.
          - This macro's external interface must transparently extend to
            fbpkg bundles -- or we'd have to add Contbuild support twice.
        That said, there are a few options that remain to be exposed,
        see "Future work" below.


    ## Future non-work

    The following `BuildCommand` arguments will never be supported:

      - `*build_command` or `build_manifest_command` or `token_defaults` or
        `mode`.  TARGETS files offer a full-featured language that is much
        safer than shell scripts -- we will not hand our users a footgun.

      - `path_mapping*` -- `path_actions` provides the equivalent
        functionality without the mental juggling.


    ## Future work

      - (hi-pri) Integrate with contbuild.  We will need to allow passing
        --tags, and may want to support --no-publish and --verbose.  The
        --json flag is already supported for easier contbuild compatibility.

      - (hi-pri) Default to a mode where we don't publish ephemerals from
        unclean trees.  My favorite implementation would be to add an
        `unclean_suffix`, which puts non-trunk builds into a separate
        package name.  See `class HGInfo` up to `_local_changes`.

      - (mid-pri) Support `log_paths` -- it can probably be reasonably be
        defaulted to the subtree declaring the `fbpkg_builder`.

      - (blocked on T38118278, mid-pri) Once `fbpkg build` is guaranteed to
        always produce a new version, we can remove most of the shenanigans
        for duplicate package & expiry handling, including the
        `--silent-duplicate-error`, `fbpkg expire --extend-only`, and
        perfaps replacing `expire_seconds_from_now` with a more
        fbpkg-compatible `expire = "7d"` kwarg.

      - (lo-pri) The current implementation will break and require `buck
        clean` or a rebuild if the repo's absolute path changes (due to a
        move / rename).  The reason is that we write the output of
        `$(location ...)` macros into the script.  Buck will eventually
        provide a better way of accessing `sh_binary` `resources`, see
        T38103077.  More context here:
            https://fb.facebook.com/groups/askbuck/permalink/2235552209826715
        NB: Unfortunately, D13050162 does not fully address the problem.

      - (once needed) Support `pre_compressed` packages, as well as
        compression type & level.  Like most other fbpkg options, we will
        not add runtime CLI arguments for changing compression options --
        all these settings will be available through TARGETS only.

      - (once needed) Bundle support (perhaps a separate rule type? TBD)
        IMPORTANT: We would want to make this work with package -> contbuild
        mapping in `SandcastleGetContbuildForPackageTrait`.  My favorite
        idea is to name the bundle target via an (ideally, lexicographically
        sorted) enumeration of all the packages it builds, separated by a
        delimiter that is fine in target names, but not fine in package
        names (I think "," has this property).  This discourages people from
        making very large bundles (via filename length limits, e.g.), but
        that's probably for the best.

      - (if needed) Support `--message`, probably ONLY as a rule argument.

      - (if needed) If I understand Buck correctly, changes to this macro
        file will necessarily result in all `fbpkg_builder` rule artifacts
        being invalidated and needing a rebuild.  This is, of course,
        desirable for correct development: change the macro, `buck build` an
        `fbpkg_builder`, see a difference in behavior.  If this stops being
        the case (e.g.  due to macro behaviors that are not reflected in the
        resulting `genrule` command), just `export_file` this and add this
        in a no-op location in our script: `$(location :fbpkg.bzl)`, or
        check out `fake_macro_library` if this grows complex dependencies.
    """

    path_actions = path_actions or {}

    source_targets = {}  # A set of target paths, the values are ignored
    symlink_num = 0  # A unique ID for each symlink we make

    # This trifecta of containers is used at `buck run` time.  Some paths
    # may contain `$(location ...)` Buck macros, while others may refer to
    # `$symlink_dir`, which is set in `fbpkg_build.sh`.
    symlink_cmds = []  # Commands to create within-fbpkg symlinks

    # These two are written into "fake configerator JSON" by `fbpkg_build.sh`
    quoted_paths = []  # fbpkg BuildConfig.paths
    quoted_flat_path_mapping = []  # fbpkg BuildConfig.path_mapping

    # `fbpkg` forces some fairly fragile time handling on us, so ints
    # are the only accepted option.
    if type(expire_seconds_from_now) != type(123):
        fail("expire_seconds_from_now must be an integer")

    # Don't let people build fbpkgs in dev modes.  This currently also
    # excludes dbgo-cov and opt-cov because those build inplace Python;
    # https://fb.facebook.com/groups/fbcode/permalink/2000943153275847/
    #
    # Dev modes must not be excluded at parse time, because as per
    # @markisaa, the contract is "If you want to run in Sandcastle, your
    # build rule needs to appear in dev mode."
    #   fb.facebook.com/groups/fbcode.foundation/permalink/1522831957819271
    # This **could** be made to fail at build-time, but that's ugly because
    # I think that would break building `path/...`, which is desirable since
    # contbuild projects usually build `...` of a subtree, even on diffs
    # (which only build in dev mode) So, it's best to fail at runtime.
    cpp_lib = native.read_config("defaults.cxx_library", "type")
    python_pkg = native.read_config("python", "package_style")
    if not allow_nonportable_artifacts and (
        cpp_lib == "shared" or python_pkg == "inplace"
    ):
        runtime_failure = "echo {} | fold -s >&2\nexit 1".format(shell.quote((
            "Your Buck build mode @{build_mode} produces {cpp_lib} C++ " +
            "artifacts, and {python_pkg}-packaged Python artifacts. At least " +
            "one of these is non-portable (i.e. cannot be used in the absence " +
            "of your current repo) and will be broken in production. If you " +
            "are 100% confident your build does not include any C, C++, or " +
            "Python, you may try setting `allow_nonportable_artifacts = " +
            "True` to allow building fbpkgs from this mode."
        ).format(
            build_mode = config.get_build_mode(),
            cpp_lib = cpp_lib,
            python_pkg = python_pkg,
        )))
    else:
        runtime_failure = ""

    for pkg_path, (action, spec) in path_actions.items():
        if action == "copy":
            # It can be pretty inefficient to copy the same artifact into the
            # package twice -- and we support symlinks -- so let's forbid it.
            #
            # Future: Canonicalize the target path, right now we won't catch
            # duplication via `:foo` vs `//full/path/to:foo`.
            if spec in source_targets:
                fail("Source path {} used twice".format(spec), "path_actions")
            source_targets[spec] = 1
            quoted_src = "$(location {})".format(spec)
        elif action == "symlink":
            # Each symlink should point at some in-package path defined by
            # this target.  The other behaviors that fbpkg supports makes no
            # sense in Buck.  Emitting fixed out-of-package symlinks would
            # be "valid" from the point of view of Buck, but the fbpkg
            # implementation precludes that.
            #
            # Design note: Why are symlinks made at `buck run` time?  The
            # main reason is that I don't trust Buck caches to do work
            # correctly with these.  For directory outputs, Buck doesn't
            # just make a tarball of the directory, it actually treats each
            # file as a separate artifact, and copies that to the cache.
            # There is no special handling for symlinks.  There are some
            # other bloviations on the subject on the following thread, but
            # the above reason is by far the most important.
            # https://fb.facebook.com/groups/askbuck/permalink/2230894016959201/
            target_action, target_spec = path_actions.get(spec, (None, None))
            if target_action != "copy":
                fail(
                    "Symlink {} -> {} must point at a 'copy' path_action"
                        .format(pkg_path, spec),
                    "path_actions",
                )

            # We'll make all symlinks in a single directory, just before
            # running `fbpkg build`.  Their names don't matter, they just
            # have to be unique.
            quoted_src = '"$symlink_dir"/{}'.format(symlink_num)
            symlink_num += 1
            symlink_cmds.append("ln -s  $(location {}) {}".format(
                target_spec,
                quoted_src,
            ))
        else:
            fail("Invalid action: {}".format(action), "path_actions")
        quoted_paths.append(quoted_src)
        quoted_flat_path_mapping.extend([quoted_src, shell.quote(pkg_path)])

    fb_native.genrule(
        name = name + "-build-script",
        out = "build_fbpkg.sh",
        # Simply writes the build script to be executed by `buck run`.
        bash = '''\
set -ue -o pipefail
cat <<'BUILD_FBPKG_EOF' > "$OUT"
#!/bin/bash -ue
set -o pipefail
{runtime_failure}

# We always use --json internally, but output pkg:uuid by default.
print_json=0
while [[ $# -ne 0 ]] ; do
    if [[ "$1" == "--json" ]] ; then
        print_json=1
    else
        echo "Unsupported fbpkg option $1" >&2
        exit 1
    fi
    shift
done

# `fbpkg build --expire` takes only deltas of the form `<number><unit>'
# relative to **now**, while `fbpkg expire` takes deltas relative to
# **package creation time** and falls back to Python `parsedatetime` to
# parse an absolute time.  Our semantics are always "relative to now", so
# for `fbpkg expire` we MUST use an absolute timestamp, and that timestamp
# had better not contain any of the letters known to the gratuitously
# over-matching `libfb.py.human_readable.parse_time_delta`.
expire_date_time=\\$(date -d "{expire_sec} seconds" +'%Y-%m-%d %H:%M:%S')

symlink_dir=\\$(mktemp -d)
fake_cfgr_dir=\\$(mktemp -d)
trap 'rm -rf "$symlink_dir" "$fake_cfgr_dir"' EXIT

# Create the symlinks
{symlink_cmds}

# We need these arrays because `location` won't expand in \\$( ... )
paths=( {quoted_paths} )
flat_path_map=( {quoted_flat_path_mapping} )

# The strings in `paths` and `path_mapping` must be shell-interpreted to
# expand the "$symlink_dir" environment variable.  We then use Python to
# JSON-serialize the result.  This incidentally also prevents quoting issues
# in the event that the Buck macro expands to something that contains
# characters for which shell quoting is incompatible with JSON quoting.

json_paths=\\$(python3 -c '
import json, sys;json.dump(sys.argv[1:], sys.stdout)' "${{paths[@]}}")

json_path_mapping=\\$(python3 -c '
import json, sys;
assert len(sys.argv) % 2 == 1, sys.argv
it = iter(sys.argv[1:])
json.dump(dict(zip(it, it)), sys.stdout)
' "${{flat_path_map[@]}}")

# Write a fake BuildConfig for our fbpkg
json_dir="$fake_cfgr_dir/materialized_configs"
mkdir -p "$json_dir"
cat <<JSON_EOF > "$json_dir/{name}.fbpkg.materialized_JSON"
{{
    "paths": $json_paths,
    "path_mapping": $json_path_mapping
}}
JSON_EOF

# See the docblock on the rationale for the various options.
pkg_json=\\$(
    fbpkg build  --silent-duplicate-error --ephemeral --yes --json \
        --configerator-path "$fake_cfgr_dir" --expire {expire_sec}s {name}
)
pkg_and_uuid=\\$(echo "$pkg_json" | python3 -c '
import json, sys
for d in json.load(sys.stdin):
    print(d["package"] + ":" + d["uuid"])
')

# This package may have been built by a prior run, and might be expiring
# soon, so extend its lifetime.  Yes, this is racy, no I don't know of a way
# around the race.  If we lose the race (or the package reaches its maximum
# lifetime -- we do not automatically set `ephemeral_limit`), the package
# will be deleted, and this will fail.  In principle, I could add retries
# for this, but this can be deleted once T38118278 makes all builds unique.
#
# Ignore the exit code in case we built something bitwise identical to a
# preserved package.  This exits with code 1:
#   $ fbpkg expire --extend-only fb-drip:1 5d
#   fb-drip:1 is not ephemeral
fbpkg expire --extend-only "$pkg_and_uuid" "$expire_date_time" >&2 ||
    echo "Proceeding although 'fbpkg expire' exited with $?"

if [[ $print_json -eq 1 ]] ; then
    echo "$pkg_json"
else
    echo "$pkg_and_uuid"
fi
BUILD_FBPKG_EOF
chmod u+x "$OUT"
        '''.format(
            name = name,
            symlink_cmds = "\n".join(symlink_cmds),
            quoted_paths = " ".join(quoted_paths),
            quoted_flat_path_mapping = " ".join(quoted_flat_path_mapping),
            runtime_failure = runtime_failure,
            expire_sec = expire_seconds_from_now,
        ),
        # We write absolute paths from the current repo (as generated by
        # $(location ...) macros) into the resulting script.  This is
        # emphatically not cacheable.  But, rebuilding the script is cheap.
        # "Future work" has a note about how a Buck feature could fix this.
        cacheable = False,
        type = "fbpkg_builder_contents",
        visibility = get_visibility(visibility, name),
    )

    # Discussion of the merits of `sh_binary` vs `command_alias`:
    #   https://fb.facebook.com/groups/askbuck/permalink/2230894016959201/
    #   https://fb.facebook.com/groups/askbuck/permalink/2235552209826715/
    # The best thing about `sh_binary` here is that it avoids copying our
    # dependent targets' outputs -- the `fbpkg build` process gets to access
    # them at their original paths in `buck-out`.
    fb_native.sh_binary(
        name = name,
        main = ":{}-build-script".format(name),
        resources = source_targets.keys(),
        visibility = get_visibility(visibility, name),
    )
