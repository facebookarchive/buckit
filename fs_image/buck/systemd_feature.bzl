load(":image_feature.bzl", "image_feature")

# Creates an image feature named "disable-<unit>" which disables the
# given systemd unit
def disable_systemd_unit_feature(
        # Systemd unit to disable (e.g. sshd.service)
        unit):
    image_feature(
        name = "disable-" + unit,
        symlinks_to_files = [
            (
                "/dev/null",
                "/etc/systemd/system/" + unit,
            ),
        ],
    )
