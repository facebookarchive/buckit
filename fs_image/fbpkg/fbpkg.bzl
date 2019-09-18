# IMPORTANT: This file is temporarily being synced to open-source. Do
# not put any implementation details in here.
#
# Eventually, `fs_image/fbpkg` will get filtered out of the open-source
# release (and then we can move everything from `fs_image/fbpkg/facebook` to
# `fs_image/fbpkg`.  We have this transitional state because recent ShipIt
# refactors made it very onerous to change the BuckIt path mapping
# configuration.  The timeline for fixing this SNAFU is whenever `fs_image`
# moves to its own repo.  Details on how to update the ShipIt config:
# https://fburl.com/r6rq0vtw
load("//fs_image/fbpkg/facebook:fbpkg.bzl", _fbpkg = "fbpkg")

fbpkg = _fbpkg
