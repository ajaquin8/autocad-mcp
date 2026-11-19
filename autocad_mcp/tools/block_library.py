"""Block definitions: make or redefine one from objects in the drawing (define_block).

It copies with CopyObjects (deep cloning, AutoCAD 2027 ActiveX reference), so layers, linetypes
and text styles the objects use come along. Not live-verified yet.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, objects, point, rounded, xyz
from ..session import session
from .draw import Point
from .entities import by_handle
from .entities import handles as split_handles

BAD_NAME = re.compile(r'[<>/\\":;?*|,=`]')
ORIGINALS = ("keep", "delete", "replace")
DRAWING_FILES = (".dwg", ".dwt", ".dws")


def check_block_name(name: str) -> str:
    text = str(name)
    if not text.strip() or text != text.strip() or len(text) > 255 or BAD_NAME.search(text):
        raise ValueError(f"'{name}' is not a usable block name (1 to 255 characters, no leading or trailing "
                         'spaces, none of < > / \\ " : ; ? * | , = `).')
    return text


def find_block(doc: Any, name: str) -> Any | None:
    try:
        return doc.Blocks.Item(name)
    except pywintypes.com_error:
        return None


def free_name(doc: Any, base: str) -> str:
    """base, or base2, base3 ... whichever is not a block in doc yet."""
    candidate, n = base, 1
    while find_block(doc, candidate) is not None:
        n += 1
        candidate = f"{base}{n}"
    return candidate


def require_editor_closed(doc: Any) -> None:
    with contextlib.suppress(pywintypes.com_error, TypeError, ValueError):
        if int(doc.GetVariable("BLOCKEDITOR")) == 1:
            raise AcadError("The Block Editor is open; close it first (close_block_editor).")


def contents(block: Any) -> list:
    return [block.Item(i) for i in range(block.Count)]


def plain_block(block: Any, what: str) -> None:
    if bool(block.IsLayout) or bool(block.IsXRef) or str(block.Name).startswith("*"):
        raise AcadError(f"'{block.Name}' is a layout, an xref or an anonymous block; {what} only works on named "
                        "block definitions.")


def space_of(doc: Any, owner_id: int) -> Any:
    """Model space or the sheet's paper space block that owns objects with this OwnerID."""
    if int(doc.ModelSpace.ObjectID) == owner_id:
        return doc.ModelSpace
    layouts = doc.Layouts
    for i in range(layouts.Count):
        block = layouts.Item(i).Block
        if int(block.ObjectID) == owner_id:
            return block
    raise AcadError("The objects are not in model space or on a sheet (are they inside a block definition?).")


@acad_tool()
def define_block(block: str, handles: list[str] | str, base_point: Point, redefine: bool = False,
                 originals: str = "keep", name: str = "") -> dict:
    """Make a block definition from objects in the drawing, with base_point as its insertion
    point, or replace the contents of an existing one (redefine=True; its references update).
    The objects are copied into the definition, from whichever space they are in, so it
    does not matter which layout tab is active. Attribute definitions among them become
    the block's attributes. One undo step: a failure leaves the drawing as it was.

    Args:
        block: the block's name.
        handles: the objects, e.g. ["2A3", "2A4"] or "2A3, 2A4"; all in the same space
            (model space or one sheet).
        base_point: [x, y] that becomes the block's insertion point.
        redefine: replace the contents of an existing block of that name (default False:
            refused if it exists). Dynamic blocks are refused (their parameters would be
            lost); bring a new version in with import_blocks(overwrite=True) instead.
            References keep their old attributes until ATTSYNC.
        originals: what happens to the objects: "keep" (default), "delete", or "replace"
            (deleted and replaced by one reference to the block at base_point).
        name: which open drawing (default: active).
    """
    check_block_name(block)
    if originals not in ORIGINALS:
        raise ValueError(f"originals is one of {', '.join(ORIGINALS)}.")
    wanted = split_handles(handles)
    if not wanted:
        raise ValueError("Give at least one handle.")
    base = xyz(base_point)
    doc = session.document(name)
    require_editor_closed(doc)
    items = [by_handle(doc, h) for h in wanted]
    owners = {int(o.OwnerID) for o in items}
    if len(owners) > 1:
        raise AcadError("The objects are in different spaces (model space and a sheet, or two sheets); "
                        "AutoCAD copies objects from one space at a time.")
    for obj in items:
        if str(obj.ObjectName) == "AcDbBlockReference" and \
                str(getattr(obj, "EffectiveName", obj.Name)).lower() == block.lower():
            raise AcadError(f"Handle {obj.Handle} is a reference to '{block}' itself; a block cannot contain itself.")
    existing = find_block(doc, block)
    if existing is not None:
        if not redefine:
            raise AcadError(f"A block named '{block}' already exists. Pass redefine=True to replace its contents "
                            "(its references update), or choose another name.")
        plain_block(existing, "define_block")
        if bool(existing.IsDynamicBlock):
            raise AcadError(f"'{block}' is a dynamic block; redefining it from plain objects would drop its "
                            "parameters and actions. Use import_blocks(overwrite=True) with a drawing that holds "
                            "the new version.")
    space = space_of(doc, owners.pop()) if originals == "replace" else None
    with session.edit(doc) as change:
        if existing is None:
            target = change.add(doc.Blocks.Add(point(base), block))
        else:
            target = existing
            old_items = contents(target)
            old_origin = tuple(target.Origin)
            backup = change.add(doc.Blocks.Add(point(old_origin), free_name(doc, f"{block}$amcp-backup")))
            if old_items:
                doc.CopyObjects(objects(old_items), backup)

            def restore(target=target, backup=backup, origin=old_origin) -> None:
                for item in reversed(contents(target)):
                    item.Delete()
                kept = contents(backup)
                if kept:
                    doc.CopyObjects(objects(kept), target)
                target.Origin = point(origin)
            change.on_rollback(restore)
            for item in old_items:
                item.Delete()
            target.Origin = point(base)
        copies = doc.CopyObjects(objects(items), target)
        result = {"block": block, "base_point": rounded(base), "objects": len(copies or ()),
                  "redefined": existing is not None, "originals": originals}
        if space is not None:
            ref = change.add(space.InsertBlock(point(base), block, 1.0, 1.0, 1.0, 0.0))
            result["reference"] = str(ref.Handle)
        if existing is not None:
            backup.Delete()
            change.created[:] = [o for o in change.created if o is not backup]
            doc.Regen(1)  # references show the new contents
            if any(str(i.ObjectName) == "AcDbAttributeDefinition" for i in items):
                result["note"] = "Existing references keep their old attributes until ATTSYNC (run_command)."
        if originals != "keep":
            # Last, because a deleted object cannot be put back if something after it failed.
            for obj in items:
                obj.Delete()
        return result
