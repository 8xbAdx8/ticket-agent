"""Small, explicit adapters for legacy and current UI result containers.

The public Trace keeps its original shape.  UI projections historically received
``list[batch]``, but restored/legacy sessions can expose a flat list, a single
dict, or a nested list.  These adapters make the data shape explicit instead of
calling ``.get`` on an arbitrary value or hiding the problem with try/except.
"""
from __future__ import annotations


def iter_rows(value):
    """Yield only dict rows from dict/flat-list/nested-list containers."""
    if isinstance(value, dict):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                yield item
            elif isinstance(item, (list, tuple)):
                yield from iter_rows(item)


def batches(value):
    """Return per-turn batches from flat or legacy nested result containers."""
    if isinstance(value, dict):
        return [[value]]
    if not isinstance(value, (list, tuple)):
        return []
    if value and all(isinstance(item, dict) for item in value):
        return [list(value)]
    output = []
    for item in value:
        if isinstance(item, dict):
            output.append([item])
        elif isinstance(item, (list, tuple)) and all(isinstance(x, dict) for x in item):
            output.append(list(item))
    return output


def as_row(value):
    """Return the first row that has a result payload, or None."""
    if isinstance(value, dict):
        return value
    for row in iter_rows(value):
        if isinstance(row.get('result'), dict):
            return row
    return None


def as_result(value):
    row = as_row(value)
    return row.get('result') if row and isinstance(row.get('result'), dict) else None
