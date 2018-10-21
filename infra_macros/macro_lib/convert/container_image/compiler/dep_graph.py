#!/usr/bin/env python3
'''
To start, read the docblock of `provides.py`. The code in this file verifies
that a set of Items can be correctly installed (all requirements are
satisfied, etc).  It then computes an installation order such that every
Item is installed only after all of the Items that match its Requires have
already been installed.  This is known as dependency order or topological
sort.
'''
from collections import namedtuple
from typing import Iterable

from .items import MultiRpmAction, PhaseOrder


# To build the item-to-item dependency graph, we need to first build up a
# complete mapping of {path, {items, requiring, it}}.  To validate that
# every requirement is satisfied, it is similarly useful to have access to a
# mapping of {path, {what, it, provides}}.  Lastly, we have to
# simultaneously examine a single item's requires() and provides() for the
# purposes of sanity checks.
#
# To avoid re-evaluating ImageItem.{provides,requires}(), we'll just store
# everything in these data structures:

ItemProv = namedtuple('ItemProv', ['provides', 'item'])
# NB: since the item is part of the tuple, we'll store identical
# requirements that come from multiple items multiple times.  This is OK.
ItemReq = namedtuple('ItemReq', ['requires', 'item'])
ItemReqsProvs = namedtuple('ItemReqsProvs', ['item_provs', 'item_reqs'])


class ValidatedReqsProvs:
    '''
    Given a set of Items (see the docblocks of `item.py` and `provides.py`),
    computes {'path': {ItemReqProv{}, ...}} so that we can build the
    DependencyGraph for these Items.  In the process validates that:
     - No one item provides or requires the same path twice,
     - Each path is provided by at most one item (could be relaxed later),
     - Every Requires is matched by a Provides at that path.
    '''
    def __init__(self, items):
        self.path_to_reqs_provs = {}

        for item in items:
            path_to_req_or_prov = {}  # Checks req/prov are sane within an item
            for req in item.requires():
                self._add_to_map(
                    path_to_req_or_prov, req, item,
                    add_to_map_fn=self._add_to_req_map,
                )
            for prov in item.provides():
                self._add_to_map(
                    path_to_req_or_prov, prov, item,
                    add_to_map_fn=self._add_to_prov_map,
                )

        # Validate that all requirements are satisfied.
        for path, reqs_provs in self.path_to_reqs_provs.items():
            for item_req in reqs_provs.item_reqs:
                for item_prov in reqs_provs.item_provs:
                    if item_prov.provides.matches(
                        self.path_to_reqs_provs, item_req.requires
                    ):
                        break
                else:
                    raise RuntimeError(
                        'At {}: nothing in {} matches the requirement {}'
                        .format(path, reqs_provs.item_provs, item_req)
                    )

    @staticmethod
    def _add_to_req_map(reqs_provs, req, item):
        reqs_provs.item_reqs.add(ItemReq(requires=req, item=item))

    @staticmethod
    def _add_to_prov_map(reqs_provs, prov, item):
        # I see no reason to allow provides-provides collisions.
        if len(reqs_provs.item_provs):
            raise RuntimeError(
                f'Both {reqs_provs.item_provs} and {prov} from {item} provide '
                'the same path'
            )
        reqs_provs.item_provs.add(ItemProv(provides=prov, item=item))

    def _add_to_map(
        self, path_to_req_or_prov, req_or_prov, item, add_to_map_fn
    ):
        # One ImageItem should not emit provides / requires clauses that
        # collide on the path.  Such duplication can always be avoided by
        # the item not emitting the "requires" clause that it knows it
        # provides.  Failing to enforce this invariant would make it easy to
        # bloat dependency graphs unnecessarily.
        other = path_to_req_or_prov.get(req_or_prov.path)
        assert other is None, 'Same path in {}, {}'.format(req_or_prov, other)
        path_to_req_or_prov[req_or_prov.path] = req_or_prov

        add_to_map_fn(
            self.path_to_reqs_provs.setdefault(
                req_or_prov.path,
                ItemReqsProvs(item_provs=set(), item_reqs=set()),
            ),
            req_or_prov,
            item
        )


def detect_rpm_action_conflicts(mras: Iterable[MultiRpmAction]):
    'Raises when a layer attempts to perform multiple actions on one RPM'
    rpm_to_actions = {}
    for mra in mras:
        for rpm in mra.rpms:
            rpm_to_actions.setdefault(rpm, []).append(mra.action)
    for rpm, actions in rpm_to_actions.items():
        if len(actions) != 1:
            raise RuntimeError(f'RPM action conflict for {rpm}: {actions}')


class DependencyGraph:
    '''
    Given an iterable of ImageItems, validates their requires / provides
    structures, and populates indexes describing dependencies between items.
    The indexes make it easy to topologically sort the items.
    '''

    def __init__(self, iter_items: 'Iterator[ImageItems]'):
        # Without deduping, dependency diamonds would cause a lot of
        # redundant work below.  Below, we also rely on mutating this set.
        items = set()
        self.order_to_phase = {}
        for item in iter_items:
            if item.phase_order is None:
                items.add(item)
            else:
                prev = self.order_to_phase.get(item.phase_order)
                self.order_to_phase[item.phase_order] = item \
                    if prev is None else prev.union(item)
                # Hack: Also add the parent layer to the topological sort
                # since it satisfies the dependency on "/" that other items
                # may have.  We'll remove it in `gen_dependency_order_items`.
                # Another fix would be to make the dependency on "/" be
                # purely implicit -- but that's more work.
                if item.phase_order is PhaseOrder.PARENT_LAYER:
                    items.add(item)
        detect_rpm_action_conflicts(
            item for item in self.order_to_phase.values()
                if isinstance(item, MultiRpmAction)
        )

        # An item is only added here if it requires at least one other item,
        # otherwise it goes in `.items_without_predecessors`.
        self.item_to_predecessors = {}  # {item: {items, it, requires}}
        self.predecessor_to_items = {}  # {item: {items, requiring, it}}

        # For each path, treat items that provide something at that path as
        # predecessors of items that require something at the path.
        for _path, rp in ValidatedReqsProvs(items).path_to_reqs_provs.items():
            for item_prov in rp.item_provs:
                requiring_items = self.predecessor_to_items.setdefault(
                    item_prov.item, set()
                )
                for item_req in rp.item_reqs:
                    requiring_items.add(item_req.item)
                    self.item_to_predecessors.setdefault(
                        item_req.item, set()
                    ).add(item_prov.item)

        # We own `items`, so reuse this set to find dependency-less items.
        items.difference_update(self.item_to_predecessors.keys())
        self.items_without_predecessors = items


# NB: The items this yields are not all actual `ImageItem`s, see the comment
# on `MultiRpmAction`. However, they all quack alike.
def gen_dependency_order_items(items):
    dg = DependencyGraph(items)

    assert PhaseOrder.PARENT_LAYER in dg.order_to_phase
    for phase in sorted(
        dg.order_to_phase.values(), key=lambda s: s.phase_order.value,
    ):
        yield phase

    while dg.items_without_predecessors:
        # "Install" an item that has no unsatisfied dependencies.
        item = dg.items_without_predecessors.pop()
        # We already yielded the parent layer phase above.
        if item.phase_order is not PhaseOrder.PARENT_LAYER:
            yield item

        # All items, which had `item` was a dependency, must have their
        # "predecessors" sets updated
        for requiring_item in dg.predecessor_to_items[item]:
            predecessors = dg.item_to_predecessors[requiring_item]
            predecessors.remove(item)
            if not predecessors:
                dg.items_without_predecessors.add(requiring_item)
                del dg.item_to_predecessors[requiring_item]  # Won't be used.

        # We won't need this value again, and this lets us detect cycles.
        del dg.predecessor_to_items[item]

    # Initially, every item was indexed here. If there's anything left over,
    # we must have a cycle. Future: print a cycle to simplify debugging.
    assert not dg.predecessor_to_items, \
        'Cycle in {}'.format(dg.predecessor_to_items)
