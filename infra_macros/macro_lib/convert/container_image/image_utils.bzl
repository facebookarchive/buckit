HELPER_BASE = "//tools/build/buck/infra_macros/macro_lib/convert/container_image"

def _wrap_bash_build_in_common_boilerplate(
        bash,
        volume_min_free_bytes,
        log_description):
    return """
    # CAREFUL: To avoid inadvertently masking errors, we should
    # only perform command substitutions with variable
    # assignments.
    set -ue -o pipefail

    start_time=\\$(date +%s)
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
      collected_logs="$artifacts_dir/image_build.log"
      (
          echo "\n\\$(date) --" \
            "\\$(($(date +%s) - start_time)) sec --" \
            "{log_description}\n"
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
      # Log all commands now that stderr is redirected.
      set -x
      
      {bash}
    
      # It is always a terrible idea to mutate Buck outputs after creation. 
      # We have two special reasons that make it even more terrible:
      #  - [image_layer] Uses a hardlink-based refcounting scheme, as 
      #    and keeps subvolumes in a special location.
      #  - [image_package] Speeds up the build for the `sendstream_stack`
      #    format by hardlinking duplicated outputs between targets.
      #
      # Not using "chmod -R" since Buck cleanup is fragile and cannot handle
      # read-only directories.
      find "$OUT" '!' -type d -print0 | xargs -0 chmod a-w
    ) &> "$my_log"
    """.format(
        helper_base = HELPER_BASE,
        bash = bash,
        min_free_bytes = volume_min_free_bytes,
        log_description = log_description,
    )

image_utils = struct(
    HELPER_BASE = HELPER_BASE,
    wrap_bash_build_in_common_boilerplate =
        _wrap_bash_build_in_common_boilerplate,
)
