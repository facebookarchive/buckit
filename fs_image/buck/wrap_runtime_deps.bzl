load("@fbcode_macros//build_defs:native_rules.bzl", "buck_genrule")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")

def wrap_runtime_deps_as_build_time_deps(name, target, visibility):
    """
    Wraps the `target` with a new target in the current project named `name`
    to convert its run-time dependencies to build-time dependencies.

    IMPORTANT: The resulting artifact is NOT cacheable, so if you include
    its contents in some other artifact, that artifact must ALSO become
    non-cacheable.

    This is used when `image.layer` will run `target` as part of its build
    process, or when some target needs to be executable from inside an
    `image.layer`.

    The reason for this is that due to Buck limitations, `image.layer`
    cannot directly take on runtime dependencies (more on that below), so
    the wrapper does that for us.

    Here is what would go wrong if we just passed `target` directly to
    `image.layer`.

     - For concreteness' sake, let's say that `target` needs to be
       executed by the `image.layer` build script (as is the case for
       `generator` from `tarballs`).

     - `image.layer` will use $(query_targets_and_outputs) to find the
       output path for `target`.

     - Suppose that `target`'s source code CHANGED since the last time our
       layer was built.

     - Furthermore, suppose that the output of `target` is a thin wrapper,
       such as what happens with in-place Python executables in @mode/dev.
       Even though the FUNCTIONALITY of the Python executable has changed,
       the actual build output will remain the same.

     - At this point, the output path that's included in the bash command of
       the layer's genrule has NOT changed.  The file referred to by that
       output path has NOT changed.  Only its run-time dependencies (the
       in-place symlinks to the actual `.py` files) have changed.
       Therefore, as far as build-time dependencies of the layer are
       concerned, the layer does not need to re-build: the inputs of the
       layer genrule are bitwise the same as the inputs before any changes
       to `target`'s source code.

       In other words, although `target` itself WOULD get rebuilt due to
       source code changes, the layer that depends on that target WOULD NOT
       get rebuilt, because it does not consider the `.py` files inside the
       in-place Python link-tree to be build-time inputs.  Those are runtime
       dependencies.  Peruse the docs here for a Buck perspective:
           https://github.com/facebook/buck/blob/master/src/com/facebook/
           buck/core/rules/attr/HasRuntimeDeps.java

    We could avoid the wrapper if we could add `target` as a **runtime
    dependency** to the `image.layer` genrule.  However, Buck does not make
    this possible.  It is possible to add runtime dependencies on targets
    that are KNOWN to the `image.layer` macro at parse time, since one could
    then use `$(exe)` -- which says "rebuild me if the mentioned target's
    runtime dependencies have changed".  But because we want to support
    composition of layers via features, `$(exe)` does not help -- the layer
    has to discover its features' dependencies via a query.  Unfortunately,
    Buck's query facilities of today only allow making build-time
    dependencies (not runtime dependencies).  So supporting the right API
    would require a change in Buck.  Either of these would do:

      - Support adding query-determined runtime dependencies to
        genrules -- via a special-purpose macro, a macro modifier, or a rule
        attribute.

      - Support Bazel-style providers, which would let the layer
        implementation directly access the data collated by its features.
        Then, the layer could just issue $(exe) macros for all runtime-
        dependency targets.  NB: This would bring a build speed win, too.
    """
    buck_genrule(
        name = name,
        out = "wrapper.sh",
        bash = '''
cat >> "$TMP/out" <<'EOF'
#!/bin/bash
exec $(exe {target_to_wrap}) "$@"
EOF
echo "# New output each build: \\$(date) $$ $PID $RANDOM $RANDOM" >> "$TMP/out"
chmod a+rx "$TMP/out"
mv "$TMP/out" "$OUT"
        '''.format(target_to_wrap = target),
        # We deliberately generate a unique output on each rebuild.
        cacheable = False,
        visibility = get_visibility(visibility, name),
    )
