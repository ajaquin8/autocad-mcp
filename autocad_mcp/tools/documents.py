"""Connection status and drawing management."""

from __future__ import annotations

import os

from ..app import acad_tool
from ..com import AcadError
from ..session import doc_key, session


@acad_tool(read_only=True)
def acad_status(start_if_needed: bool = False) -> dict:
    """Connect to AutoCAD and report version, open drawings and which of them this
    server may edit. Call this first.

    Args:
        start_if_needed: launch AutoCAD if it is not running (default False).
    """
    app = session.connect(start=start_if_needed) if (start_if_needed or not session.connected) else session.app
    docs = session.documents()
    active = app.ActiveDocument if docs else None
    return {
        "autocad": str(app.Version),
        "active_drawing": str(active.Name) if active is not None else None,
        "active_units": session.units(active) if active is not None else None,
        "open_drawings": [session.describe(d) for d in docs],
        "edit_guard": "off (AUTOCAD_MCP_ALLOW_ALL_EDITS)" if session.allow_all_edits else "on",
    }


@acad_tool(read_only=True)
def list_documents() -> list:
    """List open drawings (name, path, unsaved changes, read-only, editable)."""
    return [session.describe(d) for d in session.documents()]


@acad_tool()
def allow_edit_document(name: str) -> str:
    """Unlock an EXISTING drawing so drawing tools may change it.

    Only call this when the user has explicitly asked you to modify that specific
    drawing. Edits are still one undo step each.

    Args:
        name: name, file name or full path of the open drawing.
    """
    doc = session.find_document(name)
    session.unlocked.add(doc_key(doc))
    return f"'{doc.Name}' is now editable for this session."


@acad_tool()
def new_drawing(template: str = "") -> dict:
    """Create a new drawing this server may edit. It becomes the active drawing.

    Args:
        template: path to a .dwt template. Empty uses AutoCAD's default template
            (the one QNEW uses).
    """
    app = session.app
    if session.documents():
        session.require_idle()  # a new tab would interrupt the user's command
    if template:
        if not template.lower().endswith(".dwt") or not os.path.exists(template):
            raise AcadError(f"Template not found or not a .dwt: {template}")
        doc = app.Documents.Add(template)
    else:
        doc = app.Documents.Add()
    doc = session.find_document(str(doc.Name))
    session.mark_owned(doc)
    info = session.describe(doc)
    info["template"] = template or "(AutoCAD default)"
    info["units"] = session.units(doc)
    return info


@acad_tool()
def open_drawing(path: str, read_only: bool = False) -> dict:
    """Open a drawing file. It stays locked for edits until the user asks you to
    change it (allow_edit_document). A drawing that is already open is returned as it is.

    Args:
        path: full path of the .dwg.
        read_only: open it read-only.
    """
    for doc in session.documents():
        if os.path.normcase(str(doc.FullName or "")) == os.path.normcase(path):
            return {**session.describe(doc), "note": "already open; left as it is"}
    if not os.path.exists(path):
        raise AcadError(f"File not found: {path}")
    if session.documents():
        session.require_idle()
    doc = session.find_document(str(session.app.Documents.Open(path, read_only).Name))
    return session.describe(doc)


@acad_tool()
def save_document(path: str = "", overwrite: bool = False, name: str = "") -> dict:
    """Save an editable drawing, in place or to a new path (SaveAs).

    Args:
        path: new full path ending in .dwg. Empty saves in place (a never-saved
            drawing needs a path).
        overwrite: allow replacing an existing file at path.
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    session.require_editable(doc)
    session.require_idle(doc)
    if not path:
        if not doc.FullName:
            raise AcadError(f"'{doc.Name}' has never been saved; give a path.")
        doc.Save()
        return session.describe(doc)
    if not path.lower().endswith(".dwg"):
        raise AcadError("path must end in .dwg")
    same = os.path.normcase(path) == os.path.normcase(str(doc.FullName or ""))
    if os.path.exists(path) and not overwrite and not same:
        raise AcadError(f"{path} already exists. Pass overwrite=True only if the user agreed to replace it.")
    old_key = doc_key(doc)
    doc.SaveAs(path)
    session.rekey(old_key, doc)
    return session.describe(doc)


@acad_tool(destructive=True)
def close_document(name: str, discard_changes: bool = False) -> str:
    """Close a drawing this server created. Never closes the user's own drawings.

    Args:
        name: name, file name or full path of the open drawing.
        discard_changes: close even though it has unsaved changes (they are lost).
    """
    doc = session.find_document(name)
    key = doc_key(doc)
    if key not in session.owned:
        raise AcadError(f"'{doc.Name}' was not created by this server; ask the user to close it.")
    session.require_idle(doc)
    if not bool(doc.Saved) and not discard_changes:
        raise AcadError(f"'{doc.Name}' has unsaved changes. Save it first, or pass discard_changes=True "
                        "if the user agreed to lose them.")
    label = str(doc.Name)
    doc.Close(False)
    session.forget(key)
    return f"Closed '{label}'."
