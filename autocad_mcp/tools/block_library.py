"""Block definitions: make or redefine one from objects in the drawing (define_block), and bring
definitions in from another drawing, optionally replacing same-named ones (import_blocks).

Both copy with CopyObjects (deep cloning, AutoCAD 2027 ActiveX reference), so layers, linetypes,
text styles and nested blocks the objects use come along. A definition cloned whole keeps its
dynamic parameters and actions. Neither tool is live-verified yet.
"""

from __future__ import annotations

import contextlib
import os
import re
from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, objects, point, rounded, xyz
from ..session import session
from .blocks import block_props, number
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


# ---------- import_blocks ----------


def acad_release(app: Any) -> str:
    """'26' for AutoCAD 2027 ('26.0s ...'), the number ObjectDBX.AxDbDocument.<n> is registered under."""
    match = re.match(r"\s*(\d+)", str(app.Version))
    if not match:
        raise AcadError(f"Cannot tell AutoCAD's release from its version {app.Version!r}.")
    return match[1]


@contextlib.contextmanager
def source_database(path: str):
    """The drawing to read from: the open document if AutoCAD has it open, else the file read into
    memory with ObjectDBX (no tab, nothing written). Yields (database, label)."""
    for doc in session.documents():
        if os.path.normcase(str(doc.FullName or "")) == os.path.normcase(path):
            yield doc, f"'{doc.Name}' (open in AutoCAD)"
            return
    progid = f"ObjectDBX.AxDbDocument.{acad_release(session.app)}"
    try:
        dbx = session.app.GetInterfaceObject(progid)
    except pywintypes.com_error as err:
        raise AcadError(f"AutoCAD could not start {progid} to read the file without opening it: {err}") from None
    try:
        dbx.Open(path)
    except pywintypes.com_error as err:
        raise AcadError(f"Could not read {os.path.basename(path)} ({err}). Is it a drawing, and not open "
                        "elsewhere for editing?") from None
    try:
        yield dbx, os.path.basename(path)
    finally:
        del dbx  # releasing the in-memory drawing closes it


def named_blocks(db: Any) -> dict[str, Any]:
    """Lower-case name -> block for the named block definitions (no layouts, xrefs or *anonymous)."""
    found = {}
    blocks = db.Blocks
    for i in range(blocks.Count):
        block = blocks.Item(i)
        label = str(block.Name)
        if not (label.startswith("*") or bool(block.IsLayout) or bool(block.IsXRef)):
            found[label.lower()] = block
    return found


def references_to(doc: Any, block_name: str) -> list:
    """Every reference to the named definition (also dynamic ones drawn by an anonymous copy), in model
    space, on every sheet and nested in other named blocks."""
    wanted = block_name.lower()
    refs = []
    blocks = doc.Blocks
    owners = [blocks.Item(i) for i in range(blocks.Count)]
    for owner in owners:
        label = str(owner.Name)
        if label.startswith("*") and not bool(owner.IsLayout):
            continue  # anonymous copies of dynamic blocks, dimensions, hatches
        if bool(owner.IsXRef):
            continue
        for item in contents(owner):
            if str(item.ObjectName) != "AcDbBlockReference":
                continue
            if str(getattr(item, "EffectiveName", item.Name)).lower() == wanted:
                refs.append(item)
    return refs


def shown_values(ref: Any) -> dict[str, Any]:
    """The values a user set on a dynamic reference: shown, writable properties."""
    return {str(p.PropertyName): p.Value for p in block_props(ref).values() if bool(p.Show) and not bool(p.ReadOnly)}


def restore_values(ref: Any, values: dict[str, Any]) -> list[str]:
    """Set dynamic property values again where the new definition still has them; the rest is returned."""
    lost = []
    for prop_name, value in values.items():
        prop = block_props(ref).get(prop_name.lower())
        if prop is None or bool(prop.ReadOnly):
            lost.append(prop_name)
            continue
        allowed = list(prop.AllowedValues or ())
        try:
            if allowed and not any((str(a).lower() == str(value).lower()) if isinstance(value, str)
                                   else abs(number(a) - number(value)) < 1e-6 for a in allowed):
                lost.append(prop_name)
                continue
            prop.Value = value
        except (pywintypes.com_error, ValueError, TypeError):
            lost.append(prop_name)
    return lost


def nested_names(block: Any) -> set[str]:
    return {str(getattr(i, "EffectiveName", i.Name)).lower() for i in contents(block)
            if str(i.ObjectName) == "AcDbBlockReference"}


@acad_tool()
def import_blocks(path: str, blocks: list[str] | None = None, overwrite: bool = False, name: str = "") -> dict:
    """Bring block definitions in from another drawing file (a block library), without
    opening it as a tab and without inserting anything. New definitions come in whole,
    dynamic parameters, attributes, layers and nested blocks included.

    A block the drawing already has is skipped unless overwrite=True. Then the drawing's
    definition is replaced by the library's and every reference to it (model space, sheets,
    nested in other blocks) is switched to the new one, keeping its position, scale,
    rotation, layer, attribute values and dynamic property values where the new version
    still allows them; the old definition is then deleted. References keep their old
    attributes (new attribute definitions show after ATTSYNC). Nested blocks the drawing
    already has are kept as they are unless they are listed too. One undo step.

    Args:
        path: full path of the source .dwg (or .dwt/.dws). It is only read.
        blocks: names of the blocks to bring in (default: every named block in it).
        overwrite: replace definitions the drawing already has (default False: skip them).
        name: which open drawing to bring them into (default: active); it must be one
            this server may edit.
    """
    if not path.lower().endswith(DRAWING_FILES) or not os.path.isfile(path):
        raise AcadError(f"Not found or not a drawing file: {path}")
    doc = session.document(name)
    if os.path.normcase(str(doc.FullName or "")) == os.path.normcase(path):
        raise AcadError("That is the drawing itself; give the library drawing's path.")
    session.require_editable(doc)
    require_editor_closed(doc)
    with source_database(path) as (source, label):
        library = named_blocks(source)
        if blocks is None:
            picked = list(library.values())
        else:
            unknown = [b for b in blocks if str(b).lower() not in library]
            if unknown:
                names = sorted(str(b.Name) for b in library.values())
                raise AcadError(f"{label} has no block {', '.join(map(repr, unknown))}. It has: "
                                f"{', '.join(names[:40]) or 'none'}{' ...' if len(names) > 40 else ''}.")
            picked = [library[str(b).lower()] for b in dict.fromkeys(blocks)]
        if not picked:
            raise AcadError(f"{label} has no named block definitions.")
        have = named_blocks(doc)
        new = [b for b in picked if str(b.Name).lower() not in have]
        clash = [b for b in picked if str(b.Name).lower() in have]
        replace = clash if overwrite else []
        skipped = [] if overwrite else [str(b.Name) for b in clash]
        for b in replace:
            plain_block(have[str(b.Name).lower()], "import_blocks")
        copying = new + replace
        result: dict[str, Any] = {"source": label, "imported": [str(b.Name) for b in new], "replaced": [],
                                  "skipped_existing": skipped}
        if not copying:
            result["note"] = "Nothing to bring in: every block is already in the drawing (pass overwrite=True)."
            return result
        requested = {str(b.Name).lower() for b in copying}
        kept_nested = sorted(({n for b in copying for n in nested_names(b)} - requested) & set(have))
        with session.edit(doc) as change:
            before = set(have)
            # Set the drawing's own definitions aside under a free name, so the copies take the real names.
            aside: dict[str, tuple[Any, str]] = {}
            for b in replace:
                real = str(have[str(b.Name).lower()].Name)
                old = have[real.lower()]
                spare = free_name(doc, f"{real}$amcp-old")
                old.Name = spare
                change.on_rollback(lambda o=old, n=real: setattr(o, "Name", n))
                aside[real] = (old, spare)

            # What the drawing had, under the names it has now (the replaced ones set aside).
            keep = (before - {r.lower() for r in aside}) | {spare.lower() for _, spare in aside.values()}

            def remove_added() -> None:
                # The copies, and nested definitions that came with them: deleted, nested ones last.
                for _ in range(2):
                    for label_ in set(named_blocks(doc)) - keep:
                        with contextlib.suppress(pywintypes.com_error):
                            doc.Blocks.Item(label_).Delete()
            change.on_rollback(remove_added)
            source.CopyObjects(objects(copying), doc.Blocks)
            result["nested_brought_in"] = sorted(set(named_blocks(doc)) - keep - requested)
            not_restored: dict[str, list[str]] = {}
            switched = 0
            for real, (_old, spare) in aside.items():
                for ref in references_to(doc, spare):
                    values = shown_values(ref)
                    change.on_rollback(lambda r=ref, s=spare, v=values: (setattr(r, "Name", s), restore_values(r, v)))
                    ref.Name = real
                    lost = restore_values(ref, values)
                    if lost:
                        not_restored[str(ref.Handle)] = lost
                    switched += 1
                result["replaced"].append(real)
            result["references_switched"] = switched
            if not_restored:
                result["values_not_restored"] = not_restored
            if kept_nested:
                result["nested_kept_as_they_were"] = kept_nested
            if aside:
                doc.Regen(1)
            # Last, because a deleted definition cannot be put back if something after it failed.
            leftovers = []
            for old, spare in aside.values():
                try:
                    old.Delete()
                except pywintypes.com_error:
                    leftovers.append(spare)
            if leftovers:
                result["old_definitions_left"] = leftovers
                result["note"] = ("AutoCAD would not delete the old definitions listed; they are unused now. "
                                  "Purge them after saving and reopening the drawing (-PURGE).")
        result["drawing"] = str(doc.Name)
        return result
