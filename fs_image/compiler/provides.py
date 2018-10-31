#!/usr/bin/env python3
'''
Images are composed of a bunch of Items. These are declared by the user
in an order-independent fashion, but they have to be installed in a specific
order. For example, we can only copy a file into a directory after the
directory already exists.

The main jobs of the image compiler are:
 - to validate that the specified Items will work well together, and
 - to install them in the appropriate order.

To do these jobs, each Item Provides certain filesystem features --
described in this file -- and also Requires certain predicates about
filesystem features -- described in `requires.py`.

Requires and Provides must interact in some way -- either
 (1) Provides objects need to know when they satisfy each requirements, or
 (2) Requires objects must know all the Provides that satisfy them.

The first arrangement seemed more maintainable, so each Provides object has
to define its relationship with every Requires predicate, thus:

  def matches_NameOfRequiresPredicate(self, path_to_reqs_provs, predicate):
      """
      `path_to_reqs_provs` is the map constructed by `ValidatedReqsProvs`.
      This is a breadcrumb for the future -- having the full set of
      "provides" objects will let us resolve symlinks.
      """
      return True or False
'''

from .path_object import PathObject


class ProvidesPathObject:
    __slots__ = ()
    fields = []  # In the future, we might add permissions, etc here.

    def matches(self, path_to_reqs_provs, path_predicate):
        assert path_predicate.path == self.path, (
            'Tried to match {} against {}'.format(path_predicate, self)
        )
        fn = getattr(
            self, 'matches_' + type(path_predicate.predicate).__name__, None
        )
        assert fn is not None, (
            'predicate {} not implemented by {}'.format(path_predicate, self)
        )
        return fn(path_to_reqs_provs, path_predicate.predicate)


class ProvidesDirectory(ProvidesPathObject, metaclass=PathObject):
    def matches_IsDirectory(self, _path_to_reqs_provs, predicate):
        return True


class ProvidesFile(ProvidesPathObject, metaclass=PathObject):
    'Does not have to be a regular file, just any leaf in the FS tree'
    def matches_IsDirectory(self, _path_to_reqs_provs, predicate):
        return False
