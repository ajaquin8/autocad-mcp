"""Offline tests: no AutoCAD needed. Live tests are in tests/live and run only by hand."""

from __future__ import annotations

import asyncio
import json
import math
import threading
import time

import pytest
import pythoncom
import pywintypes
from conftest import FakeBlockRef, FakeDoc, FakeDynProp, FakeEntity
from mcp.server.mcpserver.exceptions import ToolError

from autocad_mcp import com
from autocad_mcp import session as session_module
from autocad_mcp.app import _render, _where
from autocad_mcp.com import AcadError, AcadTimeout, ComWorker, deg, rad, xyz
from autocad_mcp.server import mcp
from autocad_mcp.session import Session, doc_key, product_name, session
from autocad_mcp.tools import (
    annotate,
    block_authoring,
    block_editor,
    block_library,
    blocks,
    commands,
    control,
    documents,
    draw,
    edit,
    entities,
    layers,
    plot,
    query,
    settings,
    sheets,
)

# ---------- coordinates ----------


def test_points_take_two_or_three_numbers():
    assert xyz([1, 2]) == (1.0, 2.0, 0.0)
    assert xyz((1, 2, 3)) == (1.0, 2.0, 3.0)
    for bad in ([1], [1, 2, 3, 4], "1,2", 5):
        with pytest.raises(ValueError):
            xyz(bad)


def test_point_is_a_variant_of_three_doubles():
    variant = com.point([1, 2])
    assert list(variant.value) == [1.0, 2.0, 0.0]


def test_angles():
    assert rad(90) == pytest.approx(math.pi / 2)
    assert deg(math.pi) == pytest.approx(180)


def test_polyline_points_flatten_to_xy_pairs():
    assert draw.flat_xy([[0, 0], [10, 0, 5], [10, 20]]) == [0, 0, 10, 0, 10, 20]


def test_handles_accept_a_list_or_text():
    assert entities.handles("1a, 2B;3c") == ["1A", "2B", "3C"]
    assert entities.handles(["  4d ", ""]) == ["4D"]


# ---------- COM error text ----------


def _com_error(hresult, scode=0):
    return pywintypes.com_error(hresult, "Exception occurred.", (0, None, None, None, 0, scode), None)


def test_busy_autocad_gets_an_actionable_message():
    assert "busy" in com.describe_com_error(_com_error(-2147418111))


def test_rejected_lookup_while_busy_gets_the_busy_message(monkeypatch):
    # Live 2026-11-03: inside LINE or with OPTIONS open, pywin32 raised AttributeError('<unknown>.Count').
    def rejected():
        raise AttributeError("<unknown>.Count")

    monkeypatch.setattr(session, "documents", rejected)
    with pytest.raises(ToolError, match="busy and rejected the call.*press Esc"):
        asyncio.run(mcp.call_tool("list_documents", {}))
    assert com.describe_attribute_error(AttributeError("'NoneType' object has no attribute 'x'")).startswith(
        "AttributeError: ")


def test_lost_connection_message():
    assert "Lost the connection" in com.describe_com_error(_com_error(-2147023174))


def test_inner_scode_is_reported():
    text = com.describe_com_error(_com_error(-2147352567, -2147024809))
    assert "0x80070057" in text and "invalid argument" in text


# ---------- connecting ----------


class _RunningApp:
    def __init__(self, full_name: str, name: str = "AutoCAD") -> None:
        self.FullName, self.Name, self.Visible = full_name, name, False

    def QueryInterface(self, iid):  # noqa: N802
        return self


TRUEVIEW = r"C:\Program Files\Autodesk\DWG TrueView 2027 - English\dwgviewr.exe"
ACAD_2026 = r"C:\Program Files\Autodesk\AutoCAD 2026\acad.exe"


@pytest.fixture()
def com_registry(monkeypatch):
    """Fake running objects and registered servers, keyed by ProgID (like this PC: AutoCAD 2026 + TrueView 2027)."""
    running: dict[str, _RunningApp] = {}
    servers = {"AutoCAD.Application.26": TRUEVIEW + " /Automation",
               "AutoCAD.Application.25.1": ACAD_2026 + " /Automation",
               "AutoCAD.Application": ACAD_2026 + " /Automation"}
    launched: list[str] = []

    def get_active(progid):
        if progid not in running:
            raise _com_error(-2147221021)
        return running[progid]

    def late_bound(obj):
        if isinstance(obj, str):
            launched.append(obj)
            return _RunningApp(ACAD_2026)
        return obj

    monkeypatch.setattr(session_module.pywintypes, "IID", lambda progid: progid)
    monkeypatch.setattr(session_module.pythoncom, "GetActiveObject", get_active)
    monkeypatch.setattr(session_module, "_late_bound", late_bound)
    monkeypatch.setattr(session_module, "_server_exe", lambda progid: servers.get(progid, ""))
    monkeypatch.setattr(session_module, "_registered_progids", lambda: [p for p in servers if p.count(".") > 1])
    monkeypatch.setattr(com.enums, "load", lambda app: None)
    return running, launched


def test_progids_newest_release_first(monkeypatch):
    found = ["AutoCAD.Application.24.3", "AutoCAD.Application.26", "AutoCAD.Application.25",
             "AutoCAD.Application.Notes", "AutoCAD.Application.25.1"]
    monkeypatch.setattr(session_module, "_registered_progids", lambda: found)
    assert session_module.progids() == ["AutoCAD.Application.26", "AutoCAD.Application.25.1",
                                        "AutoCAD.Application.25", "AutoCAD.Application.24.3",
                                        "AutoCAD.Application"]


def test_connect_finds_an_older_autocad(monkeypatch, com_registry):
    running, _ = com_registry
    monkeypatch.setattr(session_module, "_registered_progids", lambda: ["AutoCAD.Application.24.3"])
    running["AutoCAD.Application.24.3"] = acad = _RunningApp(r"C:\Program Files\Autodesk\AutoCAD 2024\acad.exe")
    assert Session().connect() is acad


def test_connect_skips_trueview_and_finds_autocad_2026(com_registry):
    running, _ = com_registry
    running["AutoCAD.Application.26"] = _RunningApp(TRUEVIEW, "DWG TrueView")
    running["AutoCAD.Application.25.1"] = acad = _RunningApp(ACAD_2026)
    assert Session().connect() is acad


def test_connect_with_only_trueview_open_says_so(com_registry):
    running, _ = com_registry
    running["AutoCAD.Application.26"] = _RunningApp(TRUEVIEW, "DWG TrueView")
    with pytest.raises(AcadError, match="TrueView"):
        Session().connect()


def test_launch_starts_autocad_not_trueview(com_registry):
    _, launched = com_registry
    app = Session().connect(start=True)
    assert launched == ["AutoCAD.Application.25.1"]
    assert app.Visible is True


def test_where_is_empty_outside_our_package():
    try:
        raise ValueError("boom")
    except ValueError as err:
        assert _where(err) == ""


def test_render_formats_results():
    assert _render(None) == "ok"
    assert _render("text") == "text"
    assert '"a": 1' in _render({"a": 1})


# ---------- COM worker ----------


def test_worker_runs_everything_on_one_thread():
    w = ComWorker()
    ids = {w.call(lambda: threading.get_ident()) for _ in range(5)}
    assert len(ids) == 1 and threading.get_ident() not in ids


def test_worker_times_out_without_repeating():
    w = ComWorker()
    with pytest.raises(AcadTimeout, match="do NOT repeat"):
        w.call(lambda: time.sleep(0.5), timeout=0.05)


# ---------- edit and busy guards ----------


def test_document_key_uses_the_path_once_saved():
    assert doc_key(FakeDoc("Drawing1.dwg")) == "unsaved:drawing1.dwg"
    assert doc_key(FakeDoc("Plan.dwg", r"C:\Jobs\Plan.dwg")).endswith(r"jobs\plan.dwg")


def test_user_drawings_are_locked(fake_app):
    with pytest.raises(AcadError, match="locked"):
        session.require_editable(fake_app.doc)


def test_owned_and_unlocked_drawings_are_editable(fake_app):
    session.mark_owned(fake_app.doc)
    session.require_editable(fake_app.doc)
    other = FakeDoc("Other.dwg", r"C:\x\Other.dwg")
    session.unlocked.add(doc_key(other))
    session.require_editable(other)


def test_read_only_drawing_is_refused_even_when_owned(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.ReadOnly = True
    with pytest.raises(AcadError, match="read-only"):
        session.require_editable(fake_app.doc)


def test_saving_under_a_new_path_keeps_permission(fake_app):
    session.mark_owned(fake_app.doc)
    old = doc_key(fake_app.doc)
    fake_app.doc.FullName = r"C:\scratch\New.dwg"
    session.rekey(old, fake_app.doc)
    assert session.is_editable(fake_app.doc)


def test_busy_user_blocks_edits(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.variables["CMDACTIVE"] = 1
    with pytest.raises(AcadError, match="busy"):
        session.require_idle(fake_app.doc)


def test_not_quiescent_blocks_edits(fake_app):
    fake_app.quiescent = False
    with pytest.raises(AcadError, match="not idle"):
        session.require_idle(fake_app.doc)


def test_edit_is_one_undo_group(fake_app):
    session.mark_owned(fake_app.doc)
    with session.edit(fake_app.doc):
        pass
    assert fake_app.doc.undo_log == ["start", "end"]


def test_failed_edit_deletes_what_it_created_and_restores_changes(fake_app):
    doc = fake_app.doc
    session.mark_owned(doc)
    log = []
    with pytest.raises(RuntimeError), session.edit(doc) as change:
        line = change.add(doc.ModelSpace.AddLine(com.point([0, 0]), com.point([1, 0])))
        change.add(line)  # recorded twice: still deleted once
        change.on_rollback(lambda: log.append("first"))
        change.on_rollback(lambda: log.append("second"))
        raise RuntimeError("boom")
    assert line.deleted and doc.ModelSpace.Count == 0
    assert log == ["second", "first"]
    assert doc.undo_log == ["start", "end"]


# ---------- tools against the fakes ----------


def test_draw_line_on_an_owned_drawing(fake_app):
    session.mark_owned(fake_app.doc)
    result = draw.draw_line([0, 0], [30, 40])
    assert result["type"] == "AcDbLine" and result["length"] == 50
    assert result["start"] == [0, 0, 0] and result["angle"] == pytest.approx(53.130102)


def test_draw_line_refuses_a_user_drawing(fake_app):
    with pytest.raises(AcadError, match="locked"):
        draw.draw_line([0, 0], [1, 1])
    assert fake_app.doc.ModelSpace.Count == 0


def test_unknown_layer_rolls_the_new_line_back(fake_app):
    session.mark_owned(fake_app.doc)
    with pytest.raises(AcadError, match="No layer named"):
        draw.draw_line([0, 0], [1, 1], layer="A-WALL")
    assert fake_app.doc.ModelSpace.Count == 0


def test_add_layer_creates_then_updates(fake_app):
    session.mark_owned(fake_app.doc)
    created = layers.add_layer("A-WALL", color=1, lineweight=35)
    assert created["created"] and created["color"] == 1 and created["lineweight"] == 35
    updated = layers.add_layer("a-wall", color=3, linetype="HIDDEN")
    assert not updated["created"] and updated["color"] == 3 and updated["linetype"] == "HIDDEN"
    assert fake_app.doc.Linetypes.loaded == [("HIDDEN", "acadiso.lin")]


def test_failed_new_layer_is_removed_again(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.Linetypes.Load = lambda *a: (_ for _ in ()).throw(pywintypes.com_error(-1, "no", None, None))
    with pytest.raises(AcadError, match="Linetype 'NOPE'"):
        layers.add_layer("TEMP", linetype="NOPE")
    assert "TEMP" not in fake_app.doc.Layers.items


def test_add_layer_validates_before_touching_autocad(fake_app):
    with pytest.raises(AcadError, match="Color Index"):
        layers.add_layer("X", color=300)
    with pytest.raises(AcadError, match="lineweight"):
        layers.add_layer("X", lineweight=33)


def test_move_entities_moves_by_the_offset(fake_app):
    session.mark_owned(fake_app.doc)
    line = draw.draw_line([0, 0], [1, 0])
    edit.move_entities(line["handle"], [5, 0])
    moved = fake_app.doc.HandleToObject(line["handle"]).moved
    assert moved == ((0, 0, 0), (5, 0, 0))


def test_set_text_replaces_the_words_and_keeps_the_handle_and_properties(fake_app):
    session.mark_owned(fake_app.doc)
    note = draw.add_mtext("NEW MARK. SILL AT LANTERN ROOF", [0, 0], width=40, height=2.5, layer="0")
    ent = fake_app.doc.HandleToObject(note["handle"])
    ent.Layer, ent.StyleName = "A-ANNO-NOTE", "NOTES-TEXT"
    fake_app.doc.undo_log.clear()
    out = edit.set_text(note["handle"].lower(), "SILL AT LANTERN ROOF")
    assert out["handle"] == note["handle"] and out["old_text"] == "NEW MARK. SILL AT LANTERN ROOF"
    assert out["text"] == ent.TextString == "SILL AT LANTERN ROOF"
    assert (ent.Layer, ent.StyleName, ent.InsertionPoint) == ("A-ANNO-NOTE", "NOTES-TEXT", (0, 0, 0))
    assert fake_app.doc.undo_log == ["start", "end"]  # one undo step, no regen without a field
    stamp = draw.add_text("C:\\Jobs\\Sheet.dwg", [0, -5], height=1)
    edit.set_text(stamp["handle"], '%<\\AcVar Filename \\f "%fn6">%')
    assert "regen" in fake_app.doc.undo_log


def test_set_text_refuses_other_objects_empty_text_and_locked_drawings(fake_app):
    line_handle = fake_app.doc.space._add(FakeEntity(fake_app.doc, "AcDbLine")).Handle
    text = fake_app.doc.space._add(FakeEntity(fake_app.doc, "AcDbText", TextString="OLD")).Handle
    with pytest.raises(AcadError, match="is locked"):
        edit.set_text(text, "NEW")
    session.mark_owned(fake_app.doc)
    with pytest.raises(AcadError, match="is AcDbLine, not text; set_text changes TEXT, MTEXT"):
        edit.set_text(line_handle, "NEW")
    with pytest.raises(AcadError, match="delete_entities"):
        edit.set_text(text, "")
    with pytest.raises(AcadError, match="No object with handle"):
        edit.set_text("FFFF", "NEW")
    assert fake_app.doc.HandleToObject(text).TextString == "OLD"


def test_unknown_handle_is_reported(fake_app):
    session.mark_owned(fake_app.doc)
    with pytest.raises(AcadError, match="No object with handle"):
        edit.delete_entities(["FFFF"])


def test_drawing_variables_are_set_and_validated(fake_app):
    session.mark_owned(fake_app.doc)
    assert settings.set_drawing_variables({"dimscale": 24, "DIMLUNIT": 4}) == {
        "DIMSCALE": 24.0, "DIMLUNIT": 4, "dimension_style_updated": "Standard", "dimensions_rebuilt": 0}
    assert fake_app.doc.undo_log == ["start", "style DIMSCALE=24.0", "regen", "end"]
    assert "dimension_style_updated" not in settings.set_drawing_variables({"LTSCALE": 12})
    with pytest.raises(AcadError, match="not one of"):
        settings.set_drawing_variables({"FILEDIA": 0})
    with pytest.raises(AcadError, match="whole number"):
        settings.set_drawing_variables({"LUNITS": 2.5})
    with pytest.raises(AcadError, match="between"):
        settings.set_drawing_variables({"DIMLUNIT": 9})


def test_decimal_separator_takes_a_point_or_a_comma(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.variables["DIMDSEP"] = ","  # a style made for metric drawings
    result = settings.set_drawing_variables({"DIMLUNIT": 2, "dimdsep": "."})
    assert result["DIMDSEP"] == "." and result["dimension_style_updated"] == "Standard"
    with pytest.raises(AcadError, match="'.' or ','"):
        settings.set_drawing_variables({"DIMDSEP": ";"})
    assert fake_app.doc.variables["DIMDSEP"] == "."


def test_failed_variable_change_restores_the_earlier_ones(fake_app, monkeypatch):
    session.mark_owned(fake_app.doc)
    fake_app.doc.variables["DIMSCALE"] = 1.0
    monkeypatch.setitem(settings.VARIABLES, "LTSCALE", (float, -1000, 1000, "test"))
    with pytest.raises(RuntimeError):
        settings.set_drawing_variables({"DIMSCALE": 48, "LTSCALE": -999})
    assert fake_app.doc.variables["DIMSCALE"] == 1.0
    assert fake_app.doc.undo_log[-2:] == ["style DIMSCALE=1.0", "end"]  # style re-copied after the restore


def test_save_refuses_to_overwrite(fake_app, tmp_path):
    session.mark_owned(fake_app.doc)
    target = tmp_path / "exists.dwg"
    target.write_bytes(b"")
    with pytest.raises(AcadError, match="already exists"):
        documents.save_document(str(target))


def test_new_drawing_is_fetched_again_from_the_documents_collection(fake_app):
    info = documents.new_drawing()
    assert info["name"] == "Drawing2.dwg" and info["editable"] and info["units"] == "millimeters"
    assert info["read_only"] is False


def test_release_numbers_become_product_years():
    assert product_name("25.1s (LMS Tech)") == "AutoCAD 2026"  # once read as 2025 by Claude
    assert product_name("25.0s (LMS Tech)") == "AutoCAD 2025"
    assert product_name("26.0s (LMS Tech)") == "AutoCAD 2027"
    assert product_name("24.3s (LMS Tech)") == "AutoCAD 2024"
    assert product_name("27.0s") == "AutoCAD release 27.0 (newer or older than this server knows)"
    assert product_name("unknown") == "AutoCAD (version unknown)"


def test_status_names_the_product_year(fake_app):
    status = documents.acad_status()
    assert status["autocad"] == "AutoCAD 2027" and status["autocad_version"] == "26.0s (LMS Tech)"


def _second_drawing(fake_app, switches: bool = True):
    """Drawing2.dwg open behind the active drawing; Activate brings it to the front if `switches`."""
    other = FakeDoc("Drawing2.dwg")
    docs = fake_app.Documents.docs
    docs.append(other)
    other.activated = 0

    def activate():
        other.activated += 1
        if switches:
            docs.insert(0, docs.pop(docs.index(other)))
    other.Activate = activate
    return other


def test_activate_document_switches_tabs_only_when_autocad_is_idle(fake_app):
    other = _second_drawing(fake_app)
    fake_app.doc.variables["CMDACTIVE"] = 1  # the user is in a command in the active drawing
    with pytest.raises(AcadError, match="busy"):
        documents.activate_document("Drawing2.dwg")
    assert other.activated == 0
    fake_app.doc.variables["CMDACTIVE"] = 0
    other.variables["CMDACTIVE"] = 8  # a dialog in the drawing to switch to
    with pytest.raises(AcadError, match="not switching"):
        documents.activate_document("Drawing2.dwg")
    other.variables["CMDACTIVE"] = 0
    out = documents.activate_document("drawing2.dwg")
    assert out["active"] and out["name"] == "Drawing2.dwg" and fake_app.ActiveDocument is other
    assert out["editable"] is False  # switching to a drawing does not unlock it
    again = documents.activate_document("Drawing2.dwg")
    assert again["note"] == "already the active drawing" and other.activated == 1
    with pytest.raises(AcadError, match="No open drawing"):
        documents.activate_document("Nope.dwg")


def test_activate_document_reports_when_autocad_does_not_switch(fake_app):
    _second_drawing(fake_app, switches=False)
    with pytest.raises(AcadError, match="did not switch.*click its tab"):
        documents.activate_document("Drawing2.dwg")


def test_tools_for_the_active_drawing_point_to_activate_document(fake_app):
    other = _second_drawing(fake_app)
    session.mark_owned(other)
    with pytest.raises(AcadError, match="not the active drawing.*activate_document"):
        query.zoom_extents("Drawing2.dwg")
    assert "activate_document" in documents.open_drawing.__doc__


def test_close_refuses_user_drawings(fake_app):
    with pytest.raises(AcadError, match="not created by this server"):
        documents.close_document("Drawing1.dwg")


# ---------- registry ----------


def test_every_tool_has_a_description_and_mutating_tools_are_marked():
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) >= 25
    for t in tools:
        assert t.description and t.description.strip(), t.name
    read_only = {t.name for t in tools if t.annotations and t.annotations.read_only_hint}
    assert {"acad_status", "query_entities", "get_entity", "capture_view"} <= read_only
    assert not {"draw_line", "delete_entities", "save_document"} & read_only


# ---------- leaders, radial dimensions, centre marks ----------


def test_leader_points_and_text(fake_app):
    session.mark_owned(fake_app.doc)
    info = annotate.add_leader([[1, 2], [2, 3], [4, 3]], "1/4\" DIA THRU, 4 PLACES")
    leader = fake_app.doc.HandleToObject(info["handle"])
    assert leader.points == [(1, 2, 0), (2, 3, 0), (4, 3, 0)] and info["text"] == "1/4\" DIA THRU, 4 PLACES"
    with pytest.raises(AcadError, match="two or three points"):
        annotate.add_leader([[1, 2]], "x")


def test_diameter_runs_through_the_centre_and_radius_uses_it(fake_app):
    session.mark_owned(fake_app.doc)
    dia = fake_app.doc.HandleToObject(annotate.add_radial_dimension([5, 5], [6, 5], text_override="<> THRU")["handle"])
    assert dia.chord == (6, 5, 0) and dia.far == (4, 5, 0) and dia.TextOverride == "<> THRU"
    rad_dim = fake_app.doc.HandleToObject(annotate.add_radial_dimension([5, 5], [5, 7], kind="radius")["handle"])
    assert rad_dim.center == (5, 5, 0) and rad_dim.chord == (5, 7, 0)
    with pytest.raises(AcadError, match="not at the centre"):
        annotate.add_radial_dimension([5, 5], [5, 5])


def test_center_mark_is_two_lines_in_one_undo_step(fake_app):
    session.mark_owned(fake_app.doc)
    info = draw.draw_center_mark([2, 3], 0.125, extension=0.0625)
    across, upright = (fake_app.doc.HandleToObject(h) for h in info["handles"])
    assert across.StartPoint == (1.8125, 3, 0) and across.EndPoint == (2.1875, 3, 0)
    assert upright.StartPoint == (2, 2.8125, 0) and upright.EndPoint == (2, 3.1875, 0)
    assert fake_app.doc.undo_log == ["start", "end"]


# ---------- sheets and viewports ----------


def test_list_layouts_in_tab_order_with_title_block_handles(fake_app):
    ref = fake_app.doc.paper._add(FakeEntity(fake_app.doc, "AcDbBlockReference", EffectiveName="TITLE-BLOCK"))
    layouts = sheets.list_layouts()
    assert [lay["name"] for lay in layouts] == ["Model", "Sheet1"]
    assert layouts[1]["blocks"] == [{"handle": ref.Handle, "name": "TITLE-BLOCK"}]
    assert query.query_entities(layout="sheet1")["matches"] == 1
    with pytest.raises(AcadError, match="Layouts: Sheet1, Model"):
        query.query_entities(layout="A-101")


def test_viewport_frames_the_model_area_at_the_exact_scale(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.ActiveLayout = fake_app.doc.Layouts.Item(1)  # the user was on Model
    info = sheets.add_viewport("Sheet1", [1, 1], [9, 7], view_center=[50, 20], scale=0.5)
    vp = fake_app.doc.HandleToObject(info["handle"])
    assert vp.Center == (5, 4, 0) and (vp.Width, vp.Height) == (8, 6) and vp.displayed
    assert fake_app.zoomed == ((42, 14, 0), (58, 26, 0), True)  # 8 x 6 paper at 1:2 shows 16 x 12 model
    assert (vp.StandardScale, vp.CustomScale, vp.DisplayLocked) == (1, 0.5, True)
    assert fake_app.doc.MSpace is False and fake_app.doc.ActiveLayout.Name == "Sheet1"
    assert info["layout"] == "Sheet1" and fake_app.doc.undo_log == ["start", "end"]


def _picky_mspace(fake_app, refuse_always: bool = False) -> list:
    """Make the fake drawing refuse MSpace = True like AutoCAD on a fresh sheet (GAP-014): until the
    paper view has been zoomed (or always). Returns the list of refusals."""
    refusals: list = []

    class PickyDoc(FakeDoc):
        @property
        def MSpace(self):  # noqa: N802
            return self.__dict__.get("_mspace", False)

        @MSpace.setter
        def MSpace(self, on):  # noqa: N802
            if on and (refuse_always or not getattr(fake_app, "zoomed", None)):
                refusals.append(on)
                raise _com_error(-2147352567)
            self.__dict__["_mspace"] = on

    fake_app.doc.__class__ = PickyDoc
    return refusals


def test_viewport_zooms_the_sheet_and_retries_when_autocad_has_no_active_modelspace_viewport(fake_app):
    session.mark_owned(fake_app.doc)
    refusals = _picky_mspace(fake_app)
    info = sheets.add_viewport("Sheet1", [1, 1], [9, 7], view_center=[50, 20], scale=0.5)
    vp = fake_app.doc.HandleToObject(info["handle"])
    assert len(refusals) == 1 and "regen" in fake_app.doc.undo_log
    assert fake_app.zoomed == ((42, 14, 0), (58, 26, 0), True)  # the model zoom still ran, inside the viewport
    assert (vp.StandardScale, vp.CustomScale, vp.DisplayLocked) == (1, 0.5, True)
    assert fake_app.doc.MSpace is False and fake_app.doc.ActivePViewport is vp


def test_viewport_says_what_to_check_and_rolls_back_when_autocad_keeps_refusing(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.ActiveLayout = fake_app.doc.Layouts.Item(1)  # the user was on Model
    refusals = _picky_mspace(fake_app, refuse_always=True)
    with pytest.raises(AcadError, match="would not switch into the new viewport.*Nothing was added"):
        sheets.add_viewport("Sheet1", [1, 1], [9, 7], view_center=[50, 20], scale=0.5)
    assert len(refusals) == 2 and fake_app.doc.MSpace is False
    assert fake_app.doc.paper.items == [] and fake_app.doc.ActiveLayout.Name == "Model"


def test_viewport_refuses_model_locked_drawings_and_rolls_back(fake_app):
    with pytest.raises(AcadError, match="is locked"):
        sheets.add_viewport("Sheet1", [0, 0], [1, 1], [0, 0], 1)
    session.mark_owned(fake_app.doc)
    with pytest.raises(AcadError, match="not Model"):
        sheets.add_viewport("Model", [0, 0], [1, 1], [0, 0], 1)
    fake_app.doc.ActiveLayout = fake_app.doc.Layouts.Item(1)
    with pytest.raises(AcadError, match="No layer named"):
        sheets.add_viewport("Sheet1", [0, 0], [4, 3], [0, 0], 1, layer="NOPE")
    assert fake_app.doc.paper.items == [] and fake_app.doc.ActiveLayout.Name == "Model"


def test_current_styles_switch_and_roll_back(fake_app):
    session.mark_owned(fake_app.doc)
    out = settings.set_current_styles(dimension_style="arch-dim", multileader_style="NOTES")
    assert out == {"dimension_style": "ARCH-DIM", "multileader_style": "NOTES"}
    assert fake_app.doc.ActiveDimStyle.Name == "ARCH-DIM" and fake_app.doc.variables["CMLEADERSTYLE"] == "NOTES"
    with pytest.raises(AcadError, match="The drawing has: Standard, NOTES-TEXT"):
        settings.set_current_styles(multileader_style="Standard", text_style="Arial")
    assert fake_app.doc.variables["CMLEADERSTYLE"] == "NOTES"  # nothing half-done



# ---------- busy handling: retried calls, settling new drawings, cancel ----------


def test_message_filter_retries_only_retry_later_within_the_limit():
    f = com.MessageFilter(2)
    assert f.delay(100, com.SERVERCALL_RETRYLATER) == com.RETRY_PAUSE_MS
    assert f.delay(2500, com.SERVERCALL_RETRYLATER) == com._CANCEL  # waited long enough: give up
    assert f.delay(100, 1) == com._CANCEL  # SERVERCALL_REJECTED: AutoCAD refused outright, never retried
    assert f.retries == 1


def test_message_filter_is_a_working_com_object_on_an_sta_thread():
    import ctypes

    import pythoncom
    out: dict = {}

    def run() -> None:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        try:
            f = com.MessageFilter(1)
            f.register()
            vtbl = f._vtbl
            out["retry"] = vtbl.RetryRejectedCall(f.address, None, 10, com.SERVERCALL_RETRYLATER)
            iid = ctypes.create_string_buffer(com._IID_IMESSAGEFILTER, 16)
            ppv = ctypes.c_void_p()
            out["qi"] = vtbl.QueryInterface(f.address, ctypes.addressof(iid), ctypes.byref(ppv))
            out["same"] = ppv.value == f.address
            other = ctypes.create_string_buffer(b"\x01" * 16, 16)
            out["other"] = vtbl.QueryInterface(f.address, ctypes.addressof(other), ctypes.byref(ppv))
            com.MessageFilter.unregister()
        finally:
            pythoncom.CoUninitialize()

    t = threading.Thread(target=run)
    t.start()
    t.join()
    assert out == {"retry": com.RETRY_PAUSE_MS, "qi": 0, "same": True, "other": com._E_NOINTERFACE}


def test_worker_installs_the_filter_unless_switched_off(monkeypatch):
    w = ComWorker()
    assert w.call(lambda: w.message_filter is not None)
    monkeypatch.setenv("AUTOCAD_MCP_BUSY_RETRY_SECONDS", "0")
    off = ComWorker()
    assert off.call(lambda: off.message_filter is None)


def test_new_drawing_waits_while_autocad_is_busy(fake_app, monkeypatch):
    # Live 2026-11-04: an add-in loading into the new drawing rejected calls after it first answered.
    original_add = fake_app.Documents.Add

    def add(*args):
        returned = original_add(*args)
        new = fake_app.Documents.docs[-1]
        real, new.calls = new.GetVariable, {"n": 0}

        def busy_then_ok(name):
            new.calls["n"] += 1
            if new.calls["n"] in (1, 3):  # rejected, answered, rejected again, then steady
                raise AttributeError("<unknown>.GetVariable")
            return real(name)
        new.GetVariable = busy_then_ok
        return returned

    monkeypatch.setattr(fake_app.Documents, "Add", add)
    info = documents.new_drawing()
    new = fake_app.Documents.docs[-1]
    assert info["editable"] and info["name"] == new.Name
    assert new.calls["n"] >= 6  # the count of good answers started again after the second rejection


def test_settle_gives_up_with_a_clear_message_and_passes_other_errors(fake_app, monkeypatch):
    monkeypatch.setattr(session_module, "SETTLE_TIMEOUT", 0)

    def busy():
        raise _com_error(-2147418111)
    with pytest.raises(AcadError, match="stayed busy"):
        session.settle(busy, "creating the drawing")

    def broken():
        raise AttributeError("'NoneType' object has no attribute 'Name'")
    with pytest.raises(AttributeError):
        session.settle(broken, "creating the drawing")


class _Window:
    def __init__(self, title: str) -> None:
        self.title, self.posted = title, []

    def IsWindow(self, hwnd):  # noqa: N802 - mirrors win32gui
        return True

    def GetWindowText(self, hwnd):  # noqa: N802
        return self.title

    def send(self, hwnd, text):
        self.posted.append((hwnd, text))
        return True


def test_cancel_needs_a_connection(fake_app):
    with pytest.raises(AcadError, match="acad_status first"):
        control.cancel()


def test_cancel_refuses_when_a_user_drawing_is_active(fake_app, monkeypatch):
    window = _Window("Autodesk AutoCAD 2026  Plan.dwg")
    monkeypatch.setattr(control, "win32gui", window)
    monkeypatch.setattr(control, "send_input", window.send)
    monkeypatch.setattr(session, "hwnd", 1234)
    session.mark_owned(fake_app.doc)  # Drawing1.dwg is ours, but it is not the active one
    with pytest.raises(ToolError, match="Refused.*user's own command"):
        asyncio.run(mcp.call_tool("cancel_command", {}))
    window.title = "Autodesk AutoCAD 2026  MyDrawing1.dwg"  # a longer name ending the same way
    with pytest.raises(AcadError, match="Refused"):
        control.cancel()
    assert window.posted == []


def test_cancel_sends_two_ctrl_c_when_a_server_drawing_is_active(fake_app, monkeypatch):
    # Live 2026-11-04 the title read "<product> - [Drawing35.dwg]"; ^C^C by WM_COPYDATA cleared LINE.
    window = _Window("Autodesk AutoCAD 2026 - [Drawing1.dwg]")
    monkeypatch.setattr(control, "win32gui", window)
    monkeypatch.setattr(control, "send_input", window.send)
    monkeypatch.setattr(session, "hwnd", 1234)
    session.mark_owned(fake_app.doc)
    assert "Cancelled the command in 'drawing1.dwg'" in control.cancel()
    assert window.posted == [(1234, "")]
    window.title = "Autodesk AutoCAD 2026  Drawing1.dwg"
    control.cancel()
    assert len(window.posted) == 2
    monkeypatch.setattr(control, "send_input", lambda hwnd, text: False)
    with pytest.raises(AcadError, match="did not accept"):
        control.cancel()


def _scripts_record(windows_alive=(555,), identity="100@2026-11-06T08:00:00"):
    """An ownership record as a helper script writes it: Drawing7 is not in the server's memory."""
    session_module.OWNED_RECORD.write_text(json.dumps(
        {"autocad": identity, "drawings": [{"key": "unsaved:drawing7.dwg", "window": 555}]}), encoding="utf-8")
    return lambda hwnd: 42 if hwnd == 1234 or hwnd in windows_alive else None


def test_cancel_reads_the_record_again_for_drawings_the_servers_scripts_created(fake_app, monkeypatch):
    # Live 2026-11-06: cancel_command refused in a drawing a script made, as the record was read only at connect.
    window = _Window("Autodesk AutoCAD 2026 - [Drawing7.dwg]")
    monkeypatch.setattr(control, "win32gui", window)
    monkeypatch.setattr(control, "send_input", window.send)
    monkeypatch.setattr(control, "describe_blockers", lambda hwnd: "")
    monkeypatch.setattr(session, "hwnd", 1234)
    monkeypatch.setattr(session_module.winui, "process_identity", lambda hwnd: "100@2026-11-06T08:00:00")
    monkeypatch.setattr(session_module.winui, "window_pid", _scripts_record())
    assert "Cancelled the command in 'drawing7.dwg'" in control.cancel()
    assert not session.owned  # cancelling does not make the drawing editable
    monkeypatch.setattr(session_module.winui, "window_pid", _scripts_record(windows_alive=()))
    with pytest.raises(AcadError, match="Refused"):  # its document window is gone: closed or reopened
        control.cancel()
    monkeypatch.setattr(session_module.winui, "window_pid", _scripts_record())
    monkeypatch.setattr(session_module.winui, "process_identity", lambda hwnd: "200@2026-11-06T09:00:00")
    with pytest.raises(AcadError, match="Refused"):  # another AutoCAD process wrote that record
        control.cancel()
    assert len(window.posted) == 1


class _Desktop:
    """Top-level windows for winui.blocking_dialogs: hwnd -> (pid, class, title, enabled, buttons)."""

    def __init__(self, windows: dict) -> None:
        self.windows = windows

    def pid(self, hwnd):
        return self.windows[hwnd][0] if hwnd in self.windows else None

    def EnumWindows(self, visit, extra):  # noqa: N802 - mirrors win32gui
        for hwnd in self.windows:
            visit(hwnd, extra)

    def EnumChildWindows(self, hwnd, visit, extra):  # noqa: N802
        for i, _ in enumerate(self.windows[hwnd][4]):
            visit((hwnd, i), extra)

    def IsWindowVisible(self, hwnd):  # noqa: N802
        return True

    def IsWindowEnabled(self, hwnd):  # noqa: N802
        return self.windows[hwnd][3]

    def GetClassName(self, hwnd):  # noqa: N802
        return "Button" if isinstance(hwnd, tuple) else self.windows[hwnd][1]

    def GetWindowText(self, hwnd):  # noqa: N802
        if isinstance(hwnd, tuple):
            return self.windows[hwnd[0]][4][hwnd[1]]
        return self.windows[hwnd][2]


def test_busy_errors_name_the_dialog_autocad_shows(monkeypatch):
    from autocad_mcp import winui
    desk = _Desktop({1: (42, "AfxFrame", "AutoCAD 2026", True, []),
                     2: (42, "Afx:Palette", "PROPERTIES", True, []),  # a floating palette: not a blocker
                     3: (42, "#32770", "Block - Changes Not Saved", True, ["&Save", "Discard", "Cancel"]),
                     4: (77, "#32770", "Another program", True, ["OK"])})
    monkeypatch.setattr(winui, "win32gui", desk)
    monkeypatch.setattr(winui, "window_pid", desk.pid)
    note = winui.describe_blockers(1)
    assert '"Block - Changes Not Saved" (buttons: Save, Discard, Cancel)' in note
    assert "PROPERTIES" not in note and "Another program" not in note
    desk.windows[1] = (42, "AfxFrame", "AutoCAD 2026", False, [])  # main window disabled: a modal dialog is up
    desk.windows[3] = (42, "HwndWrapper", "Insert", True, [])  # a WPF dialog, not #32770
    del desk.windows[2]
    assert '"Insert"' in winui.describe_blockers(1)
    desk.windows[3] = (42, "#32770", "Gone", False, [])  # disabled windows are not the one to answer
    assert winui.describe_blockers(1) == "" and winui.describe_blockers(None) == ""


def test_a_busy_tool_call_names_the_dialog(fake_app, monkeypatch):
    from autocad_mcp import app as app_module

    def busy(name):
        raise _com_error(-2147418111)
    monkeypatch.setattr(fake_app.doc, "GetVariable", busy)
    monkeypatch.setattr(app_module, "describe_blockers", lambda hwnd: ' AutoCAD shows the dialog "Plot".')
    with pytest.raises(ToolError, match='busy.*dialog "Plot"'):
        asyncio.run(mcp.call_tool("acad_status", {}))


def test_busy_message_says_what_is_active(fake_app):
    fake_app.doc.variables["CMDACTIVE"] = 33
    with pytest.raises(AcadError, match="a command and an AutoLISP expression"):
        session.require_idle(fake_app.doc)


def test_status_polls_retry_only_briefly():
    w = ComWorker()

    def inside():
        limit = w.message_filter.limit_ms
        with w.quick_retries():
            short = w.message_filter.limit_ms
        return limit, short, w.message_filter.limit_ms
    limit, short, after = w.call(inside)
    assert short == int(com.QUICK_RETRY_SECONDS * 1000) < limit == after


# ---------- ownership across a server restart ----------


def _restarted(app, identity):
    """A new server process connecting to the same (or another) AutoCAD."""
    fresh = Session()
    fresh._app, fresh.identity = app, identity
    return fresh


def test_owned_drawing_survives_a_server_restart(fake_app):
    session.identity = "100@2026-11-04T08:00:00"
    new = documents.new_drawing()
    fresh = _restarted(fake_app, "100@2026-11-04T08:00:00")
    assert fresh.restore_owned() == [new["name"]]
    assert fresh.is_editable(fresh.find_document(new["name"]))
    assert not fresh.is_editable(fake_app.doc)  # the user's drawing stays locked


def test_a_reopened_drawing_or_another_autocad_stays_locked(fake_app):
    session.identity = "100@2026-11-04T08:00:00"
    new = documents.new_drawing()
    docs = fake_app.Documents.docs
    docs[-1] = FakeDoc(new["name"])  # closed and opened again: same name, new document window
    assert _restarted(fake_app, "100@2026-11-04T08:00:00").restore_owned() == []
    session.mark_owned(docs[-1])
    other = _restarted(fake_app, "200@2026-11-04T09:30:00")  # AutoCAD itself was restarted
    assert other.restore_owned() == [] and not other.owned
    record = json.loads(session_module.OWNED_RECORD.read_text(encoding="utf-8"))
    assert record == {"autocad": "200@2026-11-04T09:30:00", "drawings": []}  # the stale record is dropped


def test_unlocks_are_not_kept_and_the_record_follows_save_as_and_close(fake_app):
    session.identity = "100@2026-11-04T08:00:00"
    session.unlocked.add(doc_key(fake_app.doc))  # the user's drawing, unlocked on request
    new = documents.new_drawing()
    doc = session.find_document(new["name"])
    old_key = doc_key(doc)
    doc.FullName = r"C:\Jobs\Part.dwg"
    session.rekey(old_key, doc)
    record = json.loads(session_module.OWNED_RECORD.read_text(encoding="utf-8"))
    assert [d["key"] for d in record["drawings"]] == [doc_key(doc)]
    fresh = _restarted(fake_app, "100@2026-11-04T08:00:00")
    fresh.restore_owned()
    assert not fresh.unlocked and not fresh.is_editable(fake_app.doc)
    session.forget(doc_key(doc))
    assert json.loads(session_module.OWNED_RECORD.read_text(encoding="utf-8"))["drawings"] == []


def test_no_record_without_an_autocad_identity(fake_app):
    documents.new_drawing()
    assert not session_module.OWNED_RECORD.exists()


def test_open_drawing_waits_while_autocad_is_busy_and_stays_locked(fake_app, monkeypatch, tmp_path):
    # Live 2026-11-04: the lookup right after Documents.Open failed although the drawing then opened.
    path = tmp_path / "Part.dwg"
    path.write_bytes(b"")
    original_open = fake_app.Documents.Open

    def slow_open(p, read_only=False):
        doc = original_open(p, read_only)
        real, calls = doc.GetVariable, {"n": 0}

        def busy_first(name):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AttributeError("<unknown>.GetVariable")
            return real(name)
        doc.GetVariable = busy_first
        return doc

    monkeypatch.setattr(fake_app.Documents, "Open", slow_open)
    info = documents.open_drawing(str(path))
    assert info["name"] == "Part.dwg" and info["editable"] is False and info["created_by_mcp"] is False


def test_a_registered_filter_is_kept_alive():
    import pythoncom
    kept: list = []

    def run() -> None:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        f = com.MessageFilter(1)
        f.register()
        kept.append(any(r is f for r in com._REGISTERED))
        com.MessageFilter.unregister()
        pythoncom.CoUninitialize()

    t = threading.Thread(target=run)
    t.start()
    t.join()
    assert kept == [True]


# ---------- dynamic blocks: read, set, measure ----------


def _screw(fake_app, owned: bool = True):
    from conftest import FakeBlockRef
    doc = fake_app.doc
    if owned:
        session.mark_owned(doc)
    ref = doc.space._add(FakeBlockRef(doc, "WAG-FAST-TEK-SIDE", (2.0, 3.0, 0.0)))
    return doc, ref


def test_numbers_take_decimals_and_inch_fractions():
    assert blocks.number("1 1/4") == 1.25 and blocks.number("1-1/4") == 1.25
    assert blocks.number("5/8") == 0.625 and blocks.number('2"') == 2.0 and blocks.number(0.75) == 0.75
    with pytest.raises(ValueError):
        blocks.number("long")


def test_get_block_properties_shows_what_a_user_sees(fake_app):
    _, ref = _screw(fake_app, owned=False)  # read-only: works on the user's drawings too
    info = blocks.get_block_properties(ref.Handle)
    assert [p["name"] for p in info["properties"]] == ["Size", "Length"]  # helper and Origin left out
    assert info["properties"][0]["allowed"] == ["#8-18", "#10-16", "#12-14"]
    assert info["attributes"]["CALLOUT"] == {"value": '#12-14 x 1" HWH TEK', "invisible": True}
    hidden = blocks.get_block_properties(ref.Handle, include_hidden=True)
    assert "Visibility1" in [p["name"] for p in hidden["properties"]]


def test_set_block_properties_in_order_with_fractions_and_regen(fake_app):
    doc, ref = _screw(fake_app)
    info = blocks.set_block_properties(ref.Handle, {"size": "#10-16", "Length": "1 1/4"})
    assert ref.value("Size") == "#10-16" and ref.value("Length") == 1.25
    assert {p["name"]: p["value"] for p in info["properties"]} == {"Size": "#10-16", "Length": 1.25}
    assert doc.undo_log[-2:] == ["regen", "end"]


def test_a_refused_value_puts_the_earlier_ones_back(fake_app):
    _, ref = _screw(fake_app)
    with pytest.raises(AcadError, match="not an allowed Length"):
        blocks.set_block_properties(ref.Handle, {"Size": "#8-18", "Length": 3})
    assert ref.value("Size") == "#12-14" and ref.value("Length") == 1.0
    with pytest.raises(AcadError, match="not an allowed Size; choose from #8-18"):
        blocks.set_block_properties(ref.Handle, {"Size": "#14-10"})


class _FlipProp(FakeDynProp):
    """AutoCAD keeps a flip state as a short integer and refuses a double or a long (B4)."""

    def __init__(self) -> None:
        super().__init__("Flip state1", 0, (0, 1))

    def __setattr__(self, key, value):
        if key == "Value" and "Value" in self.__dict__:
            if getattr(value, "varianttype", None) != pythoncom.VT_I2:
                raise pywintypes.com_error(-2147024809, "Invalid input", None, None)
            value = value.value
        super().__setattr__(key, value)


def test_flip_states_are_sent_as_short_integers(fake_app):
    _, ref = _screw(fake_app)
    ref.props.append(_FlipProp())
    info = blocks.set_block_properties(ref.Handle, {"Flip state1": 1})
    assert ref.value("Flip state1") == 1 and {p["name"]: p["value"] for p in info["properties"]}["Flip state1"] == 1
    blocks.set_block_properties(ref.Handle, {"flip state1": "not flipped"})
    assert ref.value("Flip state1") == 0
    blocks.set_block_properties(ref.Handle, {"Flip state1": True})
    assert ref.value("Flip state1") == 1
    # a later refusal puts the flip back, also as a short integer
    with pytest.raises(AcadError, match="not an allowed Length"):
        blocks.set_block_properties(ref.Handle, {"Flip state1": 0, "Length": 3})
    assert ref.value("Flip state1") == 1
    with pytest.raises(AcadError, match="whole number"):
        blocks.set_block_properties(ref.Handle, {"Flip state1": 0.5})
    with pytest.raises(AcadError, match="not an allowed Flip state1; choose from 0, 1"):
        blocks.set_block_properties(ref.Handle, {"Flip state1": 2})


def test_hidden_helpers_and_user_drawings_are_refused(fake_app):
    _, ref = _screw(fake_app)
    with pytest.raises(AcadError, match="hidden helper"):
        blocks.set_block_properties(ref.Handle, {"Visibility1": "#8-18"})
    blocks.set_block_properties(ref.Handle, {"Visibility1": "#8-18"}, allow_hidden=True)
    assert ref.value("Visibility1") == "#8-18"
    session.owned.clear()
    with pytest.raises(AcadError, match="locked"):
        blocks.set_block_properties(ref.Handle, {"Size": "#8-18"})


def test_insert_block_with_dynamic_properties(fake_app):
    session.mark_owned(fake_app.doc)

    class _Blocks:
        def Item(self, name):  # noqa: N802
            return name
    fake_app.doc.Blocks = _Blocks()
    info = blocks.insert_block("WAG-FAST-TEK-SIDE", [0, 0], dynamic_properties={"Size": "#8-18", "Length": 0.75})
    assert info["dynamic_properties"] == {"Size": "#8-18", "Length": 0.75}
    with pytest.raises(AcadError, match="No property 'Colour'"):
        blocks.insert_block("WAG-FAST-TEK-SIDE", [5, 0], dynamic_properties={"Colour": "red"})
    assert len(fake_app.doc.space.items) == 1  # the failed insert was rolled back


def test_insert_block_reports_what_a_dynamic_block_shows(fake_app):
    # AutoCAD's own box also counts hidden sizes (the fake returns 0,0-1,1); the tool measures instead.
    session.mark_owned(fake_app.doc)

    class _Blocks:
        def Item(self, name):  # noqa: N802
            return name
    fake_app.doc.Blocks = _Blocks()
    info = blocks.insert_block("WAG-FAST-TEK-SIDE", [2, 3], dynamic_properties={"Size": "#8-18", "Length": 2})
    assert info["bbox"] == [[1.826, 1.0], [2.174, 3.0]]
    assert [e.ObjectName for e in fake_app.doc.space.items] == ["AcDbBlockReference"]  # the copy was deleted
    plain = blocks.insert_block("WAG-FAST-TEK-SIDE", [0, 0])  # dynamic, no properties given: measured too
    assert plain["bbox"] == [[-0.216, -1.0], [0.216, 0.0]]


def test_measure_block_reports_what_is_visible_and_leaves_nothing_behind(fake_app):
    doc, ref = _screw(fake_app)
    blocks.set_block_properties(ref.Handle, {"Size": "#8-18", "Length": 2})
    before = len(doc.space.items)
    m = blocks.measure_block(ref.Handle, include_geometry=True)
    assert m["extents"]["width"] == 0.348 and m["extents_from_insertion_point"]["min"] == [-0.174, -2.0]
    assert m["counts"] == {"AcDbAttributeDefinition": 1, "AcDbLine": 2}
    assert m["geometry"][1] == {"type": "AcDbLine", "start": [2.0, 3.0], "end": [2.0, 1.0]}
    assert len(doc.space.items) == before  # the exploded copy was deleted
    session.owned.clear()
    with pytest.raises(AcadError, match="locked"):
        blocks.measure_block(ref.Handle)



# ---------- run_command: one command with its answers, never left waiting ----------


def _lisp_tokens(text):
    """Parentheses depth over an AutoLISP text, skipping strings (to check what build_lisp makes)."""
    depth, i, strings = 0, 0, []
    while i < len(text):
        c = text[i]
        if c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                buf.append(text[j])
                j += 1
            strings.append("".join(buf))
            i = j
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            assert depth >= 0
        i += 1
    return depth, strings


def test_command_lisp_is_one_balanced_expression_with_names_as_strings():
    lisp = commands.build_lisp("_.-BEDIT", ['Door "FIXED" - Unit \\ x', [12, 3.5], 1, ""], r"C:\Temp\run.txt", False)
    depth, strings = _lisp_tokens(lisp)
    assert depth == 0 and lisp.startswith("(progn") and lisp.endswith("(princ))")  # no trailing Enter
    assert 'Door "FIXED" - Unit \\ x' in strings and "C:/Temp/run.txt" in strings and "_.-BEDIT" in strings
    assert "(amcp:in 2 (trans (list 12.0 3.5 0.0) 0 1))" in lisp  # WCS point converted to the UCS
    assert '(amcp:in 4 "")' in lisp and '"_Mark"' not in lisp  # no UNDO mark around BEDIT
    marked = commands.build_lisp("_.BPARAMETER", ["_L"], "t.txt", True)
    assert '(command "_.UNDO" "_Mark")' in marked and '(command "_.UNDO" "_Back")' in marked
    assert '(setvar "OSMODE" 0)' in marked and "(amcp:restore)" in marked


def test_command_answers_cover_objects_and_selections():
    assert commands.lisp_input({"handle": "2a"}) == '(handent "2A")'
    assert commands.lisp_input({"handle": "2A", "point": [1, 2]}) == \
        '(list (handent "2A") (trans (list 1.0 2.0 0.0) 0 1))'
    assert commands.lisp_input({"last": True}) == "(entlast)"
    assert commands.lisp_input({"select_all": "lwpolyline,dimension"}) == \
        '(ssget "_X" (list (cons 0 "LWPOLYLINE,DIMENSION")))'
    assert commands.lisp_input(0.1) == "0.1" and commands.lisp_input(1e-7) == "0.0000001"
    assert commands.lisp_input({"window": [[0, 0], [1, 1]]}) == \
        '(ssget "_W" (trans (list 0.0 0.0 0.0) 0 1) (trans (list 1.0 1.0 0.0) 0 1))'
    picked = commands.lisp_input({"handles": ["2a", "3B"], "except": "dimension"})
    assert '(handent "2A") (handent "3B")' in picked and '(wcmatch (cdr (assoc 0 (entget e))) "DIMENSION")' in picked
    assert _lisp_tokens(picked)[0] == 0 and picked.endswith("(ssadd))")
    for bad in ['(command "ERASE")', "!x", "'ZOOM", "a\nb", True, [1], {"handle": "zz"}, {"select_all": "A) (x"},
                {"what": 1}, {"crossing": [[0, 0]]}, {"handles": []}, {"handles": ["zz"]},
                {"window": [[0, 0], [1, 1]], "except": "A) (x"}, {"crossing": [[0, 0], [1, 1]], "extra": 1}]:
        with pytest.raises(ValueError):
            commands.lisp_input(bad)


def test_command_names_are_checked():
    assert commands.check_command("BPARAMETER") == "_.BPARAMETER"
    assert commands.check_command("-purge") == "_.-purge"
    assert commands.check_command("_.-BEDIT") == "_.-BEDIT"
    for bad in ["LINE 0,0", "(foo)", "", "SHELL", "-VBARUN", "saveas", "_.QUIT", "netload", "SETVAR"]:
        with pytest.raises(AcadError):
            commands.check_command(bad)


class _FakeAutoCAD:
    """Stands in for AutoCAD's command line: writes the transcript the expression would write."""

    def __init__(self, lines, never_starts=False, still_active=False, doc=None, drops=None, on_cancel=None):
        self.lines, self.never_starts, self.still_active, self.doc = lines, never_starts, still_active, doc
        self.sent, self.path, self.drops, self.on_cancel = [], None, drops, on_cancel

    def send(self, hwnd, text):
        import re
        self.sent.append(text)
        if text == "\x03\x03":  # the cancel; on_cancel: what the expression's error handler then writes
            if self.on_cancel and self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write("\n".join(self.on_cancel) + "\n")
            return True
        stage = re.search(r'\(open "([^"]+)" "[wa]"\)\) \(write-line "S\\t(\d+)"', text)
        if stage:  # a piece of the expression being stored: AutoCAD notes that it took it
            self.path = stage[1]
            if self.drops == int(stage[2]):
                return True
            with open(self.path, "a" if int(stage[2]) else "w", encoding="utf-8") as f:
                f.write(f"S\t{stage[2]}\n")
            return True
        if self.never_starts:
            return True
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")
        if self.still_active:
            self.doc.variables["CMDACTIVE"] = 1
        return True


@pytest.fixture()
def command_line(fake_app, monkeypatch, tmp_path):
    session.mark_owned(fake_app.doc)
    monkeypatch.setattr(session, "hwnd", 1234)
    monkeypatch.setattr(commands, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(commands, "START_WAIT", 0.2)
    monkeypatch.setattr(commands, "CANCEL_WAIT", 0.2)
    monkeypatch.setattr(commands, "AFTER_WAIT", 0)
    monkeypatch.setattr(commands, "POLL", 0.01)
    monkeypatch.setattr(commands, "window_title", lambda hwnd: "AutoCAD 2026 - [Drawing1.dwg]")
    monkeypatch.setattr(commands, "is_system_variable", lambda doc, name: False)

    def install(fake):
        monkeypatch.setattr(commands, "send_input", fake.send)
        return fake
    return install


def test_run_command_returns_the_transcript(fake_app, command_line):
    fake = command_line(_FakeAutoCAD(["B\t", "C\tEnter a parameter type", "P\tSpecify base point",
                                      "P\tSpecify endpoint", "D\t0"]))
    result = asyncio.run(mcp.call_tool("run_command", {"command": "BPARAMETER", "inputs": ["_L", [0, 0]]}))
    out = json.loads(result.content[0].text)
    assert out["completed"] and out["problem"] is None and out["inputs_used"] == 2
    assert [s["sent"] for s in out["steps"]] == ["_.BPARAMETER", "_L", "[0, 0]"]
    assert out["undo_mark"] and out["pieces_sent"] == len(fake.sent) >= 3
    assert fake.sent[-1] == "(eval (read amcp:src))\n" and all(m.endswith("\n") for m in fake.sent)
    assert not list(commands.RUN_DIR.iterdir())  # the transcript file is removed


def test_run_command_pairs_each_answer_with_its_prompt(fake_app, command_line):
    # E2: lines as AutoCAD 2027 logged them (AMCP-LIVE-20261118-03). The line read after an answer is the prompt
    # it replied to, with the answer echoed, unless AutoCAD printed a message after taking it.
    command_line(_FakeAutoCAD([
        "B	", "C	Current visibility state: VisibilityState0",
        "P	Enter action type [Array/Move/Scale/sTretch]: _M",
        "P	Specify selection set for action",
        "P	Select objects:   1 found",
        "P	Select objects:",
        "P	Enter angle offset <0>: 90",
        "P	Enter flip property value for an unflipped state <Not flipped>: 0,-12",
        "P	Specify endpoint:",
        "D	0"]))
    out = commands.run(fake_app.doc, "BACTION", ["_M", "_S", {"handles": ["2A"]}, "", 90, [0, -12], [60, 0]])
    assert out["steps"] == [
        {"sent": "_.BACTION", "message": "Current visibility state: VisibilityState0"},
        {"sent": "_M", "prompt": "Enter action type [Array/Move/Scale/sTretch]:"},
        {"sent": "_S", "prompt": None, "message": "Specify selection set for action"},
        {"sent": "{'handles': ['2A']}", "prompt": "Select objects:", "message": "1 found"},
        {"sent": "Enter", "prompt": "Select objects:"},
        {"sent": "90", "prompt": "Enter angle offset <0>:"},
        {"sent": "[0, -12]", "prompt": "Enter flip property value for an unflipped state <Not flipped>:",
         "answered_as": "0,-12"},
        {"sent": "[60, 0]", "prompt": "Specify endpoint:"}]
    assert "note" not in out
    assert commands.read_line(48.0, "Enter value <1>: 48") == {"prompt": "Enter value <1>:"}
    assert commands.read_line("_L", "Enter set type [None/List] <None> : _L") == {
        "prompt": "Enter set type [None/List] <None> :"}


def test_run_command_compact_result_keeps_what_matters(fake_app, command_line):
    # E1: a long build only needs whether it completed, the last prompt and lines such as "1 found".
    lines = ["B	", "C	Command: _.ERASE", "P	Select objects:   2 found", "P	Select objects:", "D	0"]
    command_line(_FakeAutoCAD(lines))
    result = asyncio.run(mcp.call_tool("run_command", {"command": "ERASE", "inputs": [{"handles": ["2A", "2B"]}, ""],
                                                       "compact": True}))
    out = json.loads(result.content[0].text)
    assert out == {"command": "_.ERASE", "drawing": "Drawing1.dwg", "completed": True, "inputs_used": 2,
                   "inputs_given": 2, "last_prompt": "Select objects:", "messages": ["answer 1: 2 found"]}
    # When it fails, the problem and the last steps come back.
    many = ["B	", "C	Command: _.LINE"] + [f"P	Specify next point or [Undo]: {i},0" for i in range(10)]
    command_line(_FakeAutoCAD(many + ["A	Specify next point or [Undo]: 9,0", "K	*Cancel*", "U	", "D	0"]))
    full = commands.run(fake_app.doc, "LINE", [f"{i},0" for i in range(10)])
    out = commands.compact_result(full)
    assert not out["completed"] and out["cancelled"] and out["undone"] and "cancelled" in out["problem"]
    assert len(out["steps"]) == commands.FAILED_STEPS and out["steps_shown"] == "the last 8 of 11"
    assert out["steps"][-1] == {"sent": "9,0", "prompt": "Specify next point or [Undo]:"}


def test_run_command_shows_the_open_prompt_only_when_autocad_printed_it(fake_app, command_line):
    # The prompt a cancelled command waited at is printed when the next input arrives, so the line before the
    # cancel repeats the last answer's prompt; that is not reported as the open prompt.
    command_line(_FakeAutoCAD(["B	", "C	Command: _.LINE", "P	Specify first point:",
                               "A	Specify first point:", "K	*Cancel*", "U	", "D	0"]))
    out = commands.run(fake_app.doc, "LINE", [[0, 0]])
    assert out["cancelled"] and out["left_waiting_at"] is None and "had not printed" in out["problem"]
    assert out["steps"][0] == {"sent": "_.LINE"}
    command_line(_FakeAutoCAD(["B	", "C	Command: _.LINE", "P	Specify first point:",
                               "A	Specify first point:", "K	Specify next point or [Undo]: *Cancel*", "U	",
                               "D	0"]))
    out = commands.run(fake_app.doc, "LINE", [[0, 0]])
    assert out["left_waiting_at"] == "Specify next point or [Undo]:" and "next point" in out["problem"]


def test_run_command_reports_an_early_end_and_a_cancel(fake_app, command_line):
    command_line(_FakeAutoCAD(["B\t", "C\tx", "P\ty", "E\t2", "U\t", "D\t0"]))
    out = commands.run(fake_app.doc, "BPARAMETER", ["_L", "Width"])
    assert not out["completed"] and out["ended_early_before_input"] == 2 and out["undone"]
    assert "ended before answer 2 of 2" in out["problem"]
    command_line(_FakeAutoCAD(["B\t", "C\tx", "P\ty", "A\tEnter number of grips [0/1/2] <2>:", "U\t", "D\t0"]))
    out = commands.run(fake_app.doc, "BPARAMETER", ["_L"])
    assert out["cancelled"] and "number of grips" in out["problem"]
    command_line(_FakeAutoCAD(["B\t", "C\tx", "N\t1", "A\tSelect objects:", "U\t", "D\t0"]))
    out = commands.run(fake_app.doc, "ERASE", [{"handle": "FFFF"}])
    assert not out["completed"] and "found nothing" in out["problem"]


def _stored_text(messages):
    """What AutoCAD would have in amcp:src after the storing messages (undoing the string escapes)."""
    import re
    out = []
    for message, _ in messages[:-1]:
        literal = re.search(r'\(setq amcp:src (?:\(strcat amcp:src )?"((?:[^"\\]|\\.)*)"', message)[1]
        out.append(re.sub(r"\\(.)", r"\1", literal))
    return "".join(out)


def test_command_expression_reaches_autocad_in_short_complete_messages():
    # AutoCAD drops a WM_COPYDATA message of 1000 characters or more, silently (live 2026-11-11).
    answers = [f'answer "{i}" \\ ' + "x" * 60 for i in range(40)]
    lisp = commands.build_lisp("_.-LAYER", answers, r"C:\Users\me\.autocad-mcp\run\t.txt", True)
    messages = commands.staged_messages(lisp, r"C:\Users\me\.autocad-mcp\run\t.txt")
    assert len(messages) > 5 and all(len(m) <= commands.MAX_MESSAGE and m.endswith("\n") for m, _ in messages)
    assert all(_lisp_tokens(m[:-1])[0] == 0 for m, _ in messages)  # each one a complete expression
    assert _stored_text(messages) == lisp
    assert [shows for _, shows in messages] == [f"S\t{i}" for i in range(len(messages) - 1)] + ["B\t"]
    assert messages[0][0].startswith('(progn (setq amcp:src "') and 't.txt" "w"))' in messages[0][0]
    assert messages[1][0].startswith('(progn (setq amcp:src (strcat amcp:src "') and 't.txt" "a"))' in messages[1][0]
    assert messages[-1][0] == "(eval (read amcp:src))\n"
    with pytest.raises(AcadError, match="path is too long"):
        commands.staged_messages(lisp, "C:/" + "d" * 800 + "/t.txt")


def test_run_command_cancels_what_it_typed_if_the_expression_does_not_start(fake_app, command_line):
    fake = command_line(_FakeAutoCAD(["B\t", "C\tx", "D\t0"], never_starts=True))
    with pytest.raises(AcadError, match=r"did not take message (\d) of \1 "):
        commands.run(fake_app.doc, "REGEN", undo_on_failure=False)
    assert fake.sent[-1] == "\x03\x03" and "\n" not in fake.sent  # no bare Enter: it would repeat a command
    fake = command_line(_FakeAutoCAD(["B\t", "C\tx", "D\t0"], drops=1))  # AutoCAD does not take the second piece
    with pytest.raises(AcadError, match="did not take message 2 of"):
        commands.run(fake_app.doc, "REGEN")
    assert len(fake.sent) == 3 and fake.sent[-1] == "\x03\x03"  # stopped there, nothing evaluated


def test_run_command_cancels_a_command_left_waiting(fake_app, command_line):
    fake = command_line(_FakeAutoCAD(["B\t", "C\tx", "D\t1"], still_active=True, doc=fake_app.doc))
    out = commands.run(fake_app.doc, "LINE")
    assert out["cancelled_afterwards"] and fake.sent[-1] == "\x03\x03"


def test_run_command_looks_again_for_a_prompt_that_comes_back(fake_app, command_line):
    # Live 2026-11-18 (AMCP-LIVE-20261118-02): SELECT in the Block Editor ended, AutoCAD answered, and a moment
    # later it was waiting at a prompt again; every later call was refused until cancel_command.
    fake = command_line(_FakeAutoCAD(["B\t", "C\tSelect objects:", "P\tSelect objects:", "D\t0"]))
    real, calls = fake_app.doc.GetVariable, {"n": 0}

    def comes_back(var):
        if var == "CMDACTIVE":
            calls["n"] += 1
            return 1 if calls["n"] >= 3 else 0  # idle before sending and at the first look, waiting at the second
        return real(var)
    fake_app.doc.GetVariable = comes_back
    out = commands.run(fake_app.doc, "SELECT", [{"handle": "8A"}], undo_on_failure=False)
    assert out["completed"] and out["cancelled_afterwards"] and fake.sent[-1] == "\x03\x03"
    assert "waiting at a prompt again" in out["problem"]


def test_run_command_gives_up_without_repeating(fake_app, command_line, monkeypatch):
    fake = command_line(_FakeAutoCAD(["B\t", "C\tx"]))  # never finishes: e.g. stuck in a dialog
    monkeypatch.setattr(commands, "describe_blockers", lambda hwnd: ' AutoCAD shows the dialog "Block".')
    with pytest.raises(AcadError, match='did not finish.*not cancelled.*do NOT repeat.*"Block"'):
        commands.run(fake_app.doc, "BCLOSE", timeout_seconds=1)
    assert fake.sent.count("(eval (read amcp:src))\n") == 1  # sent once: nothing repeated
    assert "\x03\x03" not in fake.sent  # a dialog is the user's to answer: no Ctrl+C into it


def test_run_command_cancels_a_command_that_does_not_finish(fake_app, command_line, monkeypatch):
    # B3: a Block Editor action stuck at a prompt left AutoCAD refusing every call until cancel_command.
    fake = command_line(_FakeAutoCAD(
        ["B\t", "C\tSelect parameter:", "P\tEnter action type [Array/Move/Scale/sTretch]:"],
        on_cancel=["X\tFunction cancelled", "U\t", "D\t0"]))
    with pytest.raises(AcadError) as caught:
        commands.run(fake_app.doc, "BACTION", [[1, 2], "_T"], timeout_seconds=1)
    message = str(caught.value)
    assert "did not finish within 1s" in message and "cancelled it" in message and "put back" in message
    assert "[1, 2] -> 'Enter action type" in message and "AutoCAD answers again" in message
    assert fake.sent[-1] == "\x03\x03" and fake.sent.count("(eval (read amcp:src))\n") == 1
    assert not list(commands.RUN_DIR.iterdir())  # the transcript file is removed


def test_run_command_says_when_autocad_still_refuses_after_the_cancel(fake_app, command_line, monkeypatch):
    command_line(_FakeAutoCAD(["B\t", "C\tx"]))  # the cancel does not end it
    real = fake_app.doc.GetVariable
    calls = {"n": 0}

    def refusing(name):
        if name == "CMDACTIVE":
            calls["n"] += 1
            if calls["n"] > 1:  # the first is require_idle before anything is sent
                raise AttributeError("<unknown>.GetVariable")
        return real(name)
    fake_app.doc.GetVariable = refusing
    with pytest.raises(AcadError, match="cancelled it.*still does not answer: call cancel_command"):
        commands.run(fake_app.doc, "BACTION", timeout_seconds=1, undo_on_failure=False)


def test_run_command_does_not_cancel_in_another_drawing(fake_app, command_line, monkeypatch):
    fake = command_line(_FakeAutoCAD(["B\t", "C\tx"]))
    titles = iter(["AutoCAD 2027 - [Drawing1.dwg]"])
    monkeypatch.setattr(commands, "window_title", lambda hwnd: next(titles, "AutoCAD 2027 - [Plan.dwg]"))
    with pytest.raises(AcadError, match="no longer the active drawing, so it was not cancelled"):
        commands.run(fake_app.doc, "BACTION", timeout_seconds=1)
    assert "\x03\x03" not in fake.sent


def test_run_command_keeps_the_guards(fake_app, command_line, monkeypatch):
    fake = command_line(_FakeAutoCAD(["D\t0"]))
    user = FakeDoc("Plan.dwg", r"C:\Jobs\Plan.dwg")
    with pytest.raises(AcadError, match="locked"):
        commands.run(user, "REGEN")
    fake_app.doc.variables["CMDACTIVE"] = 1
    with pytest.raises(AcadError, match="busy"):
        commands.run(fake_app.doc, "REGEN")
    fake_app.doc.variables["CMDACTIVE"] = 0
    other = FakeDoc("Drawing2.dwg")
    session.mark_owned(other)
    fake_app.Documents.docs.append(other)
    with pytest.raises(AcadError, match="not the active drawing"):
        commands.run(other, "REGEN")
    monkeypatch.setattr(commands, "window_title", lambda hwnd: "AutoCAD 2026 - [Plan.dwg]")
    with pytest.raises(AcadError, match="does not show"):
        commands.run(fake_app.doc, "REGEN")
    monkeypatch.setattr(commands, "window_title", lambda hwnd: "AutoCAD 2026 - [Drawing1.dwg]")
    fake_app.doc.variables["UNDOCTL"] = 0
    with pytest.raises(AcadError, match="UNDO is off"):
        commands.run(fake_app.doc, "REGEN")
    monkeypatch.setattr(commands, "is_system_variable", lambda doc, name: True)
    with pytest.raises(AcadError, match="system variable"):
        commands.run(fake_app.doc, "SECURELOAD2")
    assert fake.sent == []


def test_system_variables_are_told_apart_from_commands():
    class Doc:
        def GetVariable(self, name):  # noqa: N802
            if name == "OSMODE":
                return 0
            raise _com_error(-2147024809)
    assert commands.is_system_variable(Doc(), "OSMODE") and not commands.is_system_variable(Doc(), "BPARAMETER")


# ---------- Block Editor tools ----------


class _Runs:
    """Records what the Block Editor tools ask run_command to do, and answers like it would."""

    def __init__(self, doc, results=None, editor_after=None):
        self.doc, self.calls, self.results, self.editor_after = doc, [], list(results or []), editor_after or {}

    def run(self, doc, command, inputs=(), undo_on_failure=True, timeout_seconds=30.0):
        self.calls.append((command, list(inputs), undo_on_failure))
        if command in self.editor_after:
            doc.variables["BLOCKEDITOR"] = self.editor_after[command]
        result = self.results.pop(0) if self.results else {}
        base = {"completed": True, "steps": [{"sent": command, "prompt": "x"}], "inputs_used": len(inputs),
                "cancelled": False, "undone": False, "problem": None}
        return {**base, **result}


class _Blocks:
    def __init__(self, blocks):
        self.blocks = blocks

    def Item(self, name):  # noqa: N802
        if name not in self.blocks:
            raise _com_error(-2145386476)
        return self.blocks[name]


class _Definition:
    def __init__(self, items):
        self.items = items

    @property
    def Count(self):  # noqa: N802
        return len(self.items)

    def Item(self, i):  # noqa: N802
        return self.items[i]


def _editor(fake_app, monkeypatch, open_=False, **runs):
    doc = fake_app.doc
    session.mark_owned(doc)
    doc.variables["BLOCKEDITOR"] = 1 if open_ else 0
    doc.Blocks = _Blocks({"Door unit - 40": _Definition([])})
    recorder = _Runs(doc, **runs)
    monkeypatch.setattr(block_editor.commands, "run", recorder.run)
    return doc, recorder


def test_open_block_editor_passes_the_name_with_spaces_whole(fake_app, monkeypatch):
    doc, runs = _editor(fake_app, monkeypatch, editor_after={"-BEDIT": 1})
    out = block_editor.open_block_editor("Door unit - 40")
    assert out["block_editor_open"] and runs.calls == [("-BEDIT", ["Door unit - 40"], False)]
    with pytest.raises(AcadError, match="is open"):
        block_editor.open_block_editor("Door unit - 40")
    doc.variables["BLOCKEDITOR"] = 0
    with pytest.raises(AcadError, match="No block named"):
        block_editor.open_block_editor("Nope")


def test_close_block_editor_saves_and_answers_a_save_prompt(fake_app, monkeypatch):
    doc, runs = _editor(fake_app, monkeypatch, open_=True,
                        results=[{}, {"cancelled": True, "completed": False}, {}], editor_after={})
    original = runs.run

    def run(doc_, command, inputs=(), **kw):
        out = original(doc_, command, inputs, **kw)
        if command == "BCLOSE" and inputs:
            doc_.variables["BLOCKEDITOR"] = 0
        return out
    monkeypatch.setattr(block_editor.commands, "run", run)
    out = block_editor.close_block_editor()
    assert not out["block_editor_open"]
    assert [c[:2] for c in runs.calls] == [("BSAVE", []), ("BCLOSE", []), ("BCLOSE", ["_S"])]


def test_close_block_editor_reports_when_it_stays_open(fake_app, monkeypatch):
    _editor(fake_app, monkeypatch, open_=True, results=[{"completed": False, "problem": "nope"}])
    with pytest.raises(AcadError, match="Closing the Block Editor failed: nope"):
        block_editor.close_block_editor(save=False)


def test_linear_parameter_answers_in_the_live_order(fake_app, monkeypatch):
    _, runs = _editor(fake_app, monkeypatch, open_=True)
    out = block_editor.add_linear_parameter("Width", [0, 0], [48, 0], [24, -6])
    assert runs.calls == [("BPARAMETER", ["_L", "_L", "Width", [0, 0], [48, 0], [24, -6], "1"], True)]
    assert out["pick_point"] == [12.0, -6.0]  # on the parameter's line, a quarter of the way along
    assert block_editor.parameter_pick_point([0, 0], [0, 84], [-6, 42]) == [-6.0, 21.0]
    with pytest.raises(ValueError):
        block_editor.add_linear_parameter("Width", [0, 0], [48, 0], [24, -6], grips=3)


def test_linear_parameter_value_sets_follow_the_live_prompts(fake_app, monkeypatch):
    # T7, prompts recorded live 2026-11-18 (AMCP-LIVE-20261118-03): Value set comes before the start point.
    _, runs = _editor(fake_app, monkeypatch, open_=True)
    block_editor.add_linear_parameter("Width", [0, 0], [60, 0], [30, -6], value_list=[48, 60, 72.5])
    block_editor.add_linear_parameter("Height", [0, 0], [0, 84], [-6, 42], increment={"step": 6, "min": 72, "max": 96})
    (_, listed, _), (_, stepped, _) = runs.calls
    assert listed == ["_L", "_L", "Width", "_V", "_L", "48,60,72.5", [0, 0], [60, 0], [30, -6], "1"]
    assert stepped == ["_L", "_L", "Height", "_V", "_I", 6.0, 72.0, 96.0, [0, 0], [0, 84], [-6, 42], "1"]
    for bad in [{"value_list": [1], "increment": {"step": 1, "min": 0, "max": 2}},
                {"increment": {"step": 0, "min": 0, "max": 2}}, {"increment": {"step": 1, "min": 3, "max": 2}},
                {"increment": {"step": 1}}]:
        with pytest.raises(ValueError):
            block_editor.add_linear_parameter("W", [0, 0], [1, 0], [0, -1], **bad)
    assert len(runs.calls) == 2  # nothing sent for the bad ones


def test_linear_parameter_needs_the_editor_and_reports_failure(fake_app, monkeypatch):
    _editor(fake_app, monkeypatch, open_=False)
    with pytest.raises(AcadError, match="not open"):
        block_editor.add_linear_parameter("Width", [0, 0], [48, 0], [24, -6])
    fake_app.doc.variables["BLOCKEDITOR"] = 1
    _editor(fake_app, monkeypatch, open_=True,
            results=[{"completed": False, "problem": "It was waiting at 'grips'.", "undone": True}])
    with pytest.raises(AcadError, match="waiting at 'grips'.*put back"):
        block_editor.add_linear_parameter("Width", [0, 0], [48, 0], [24, -6])


def _view(doc, centre, height, screen=(1000, 500)):
    doc.variables.update({"VIEWCTR": (*centre, 0.0), "VIEWSIZE": height, "SCREENSIZE": screen})


def test_stretch_action_inputs_follow_the_live_prompts(fake_app, monkeypatch):
    doc, runs = _editor(fake_app, monkeypatch, open_=True)
    zoomed = []
    fake_app.ZoomExtents = lambda: zoomed.append(True)
    _view(doc, (30, 40), 120)  # shows x -90..150, y -20..100
    doc.variables["BACTIONBARMODE"] = 1
    out = block_editor.add_stretch_action([12, -6], [[40, -10], [60, 90]])
    (command, inputs, undo), = runs.calls
    assert command == "BACTION" and undo and zoomed and out["zoom"] == "extents"
    assert inputs == [[12, -6], "_T", "_S", [40, -10], [60, 90], {"crossing": [[40, -10], [60, 90]]}, "", [12, -6]]
    assert doc.variables["BACTIONBARMODE"] == 1  # put back
    own = block_editor.stretch_inputs([0, 0], [[0, 0], [1, 1]], {"handles": ["2A"]}, "start", None, "", None)
    assert own == [[0, 0], "_T", "_T", [0, 0], [1, 1], {"handles": ["2A"]}, "", [0, 0]]
    with pytest.raises(ValueError):
        block_editor.stretch_inputs([0, 0], [[0, 0]], None, "second", None, None, None)


def test_stretch_angle_offset_goes_before_the_location(fake_app, monkeypatch):
    # T9, prompts recorded live 2026-11-18 (AMCP-LIVE-20261118-03): O, then "Enter angle offset <0>", then location.
    doc, runs = _editor(fake_app, monkeypatch, open_=True)
    fake_app.ZoomExtents = lambda: None
    block_editor.add_stretch_action([15, -6], [[55, -10], [70, 94]], offset=90, location=[65, -20])
    (_, inputs, _), = runs.calls
    assert inputs[-3:] == ["_O", 90.0, [65, -20]]
    both = block_editor.stretch_inputs([0, 0], [[0, 0], [1, 1]], None, "second", 0.5, "", [2, 2], 45)
    assert both[-5:] == ["_M", 0.5, "_O", 45.0, [2, 2]]
    assert "_O" not in block_editor.stretch_inputs([0, 0], [[0, 0], [1, 1]], None, "second", None, "", None, 0)


def test_centred_stretch_answers_m_value_location_and_selects_in_the_current_space():
    # B1: the multiplier path removed polylines and dimensions with ssget "_X" (the whole drawing, not the
    # block being edited) and left BACTION waiting. Now they are left out of the one crossing selection.
    centre = block_editor.stretch_inputs([12, -6], [[20, -10], [28, 90]], None, "second", 0.5, None, [30, 0])
    assert centre[5:] == [{"crossing": [[20, -10], [28, 90]], "except": "LWPOLYLINE,DIMENSION"}, "",
                          "_M", 0.5, [30, 0]]
    assert not any(isinstance(a, dict) and "select_all" in a for a in centre) and "_R" not in centre
    lisp = commands.lisp_input(centre[5])
    assert lisp == ('(ssget "_C" (trans (list 20.0 -10.0 0.0) 0 1) (trans (list 28.0 90.0 0.0) 0 1) '
                    '(list (cons -4 "<NOT") (cons 0 "LWPOLYLINE,DIMENSION") (cons -4 "NOT>")))')
    assert _lisp_tokens(lisp)[0] == 0
    plain = block_editor.stretch_inputs([0, 0], [[0, 0], [1, 1]], {"window": [[0, 0], [2, 2]]}, "second", 0.5, "",
                                        None)
    assert plain[5:] == [{"window": [[0, 0], [2, 2]]}, "", "_M", 0.5, [0, 0]]


def test_stretch_action_explains_handles_from_outside_the_block_editor(fake_app, monkeypatch):
    # B2, live 2026-11-18 (AMCP-LIVE-20261118-01): inside the Block Editor a model-space handle finds nothing,
    # so BACTION stops at the selection and is put back. The error now says why.
    found_nothing = {"completed": False, "missing_object": 6, "undone": True,
                     "problem": "Answer 6 found nothing (no object with that handle, ...)."}
    doc, runs = _editor(fake_app, monkeypatch, open_=True, results=[found_nothing, found_nothing])
    fake_app.ZoomExtents = lambda: None
    with pytest.raises(AcadError, match=r"None of the handles 7C is an object of the block being edited.*new handles"
                                        r".*crossing"):
        block_editor.add_stretch_action([0, 0], [[0, 0], [1, 1]], select={"handles": ["7C"]})
    (command, inputs, _), = runs.calls
    assert inputs[block_editor.SELECTION_ANSWER - 1] == {"handles": ["7C"]}
    with pytest.raises(AcadError, match="Adding the stretch action failed: Answer 6 found nothing"):
        block_editor.add_stretch_action([0, 0], [[0, 0], [1, 1]])  # a crossing that found nothing: plain message


def test_stretch_action_widens_the_view_to_show_every_pick_point(fake_app, monkeypatch):
    doc, runs = _editor(fake_app, monkeypatch, open_=True)
    fake_app.ZoomExtents = lambda: None
    _view(doc, (0, 0), 20)  # shows x -20..20, y -10..10: the location at x 90 is off screen
    out = block_editor.add_stretch_action([0, 5], [[-5, -5], [5, 15]], location=[90, 0])
    assert out["zoom"].startswith("extents, widened")
    (lower, upper, _) = fake_app.zoomed
    assert lower[0] < -20 and lower[1] < -10 and upper[0] > 90 and upper[1] > 15
    assert block_editor.pick_points([[1, 2], "_T", {"crossing": [[3, 4], [5, 6]]}, {"handles": ["2A"]}]) == \
        [(1, 2), (3, 4), (5, 6)]


def test_lock_attribute_positions_one_undo_step(fake_app, monkeypatch):
    doc, _ = _editor(fake_app, monkeypatch)
    a, b = FakeEntity(doc, "AcDbAttributeDefinition", TagString="MARK", LockPosition=False), \
        FakeEntity(doc, "AcDbAttributeDefinition", TagString="SIZE", LockPosition=True)
    doc.Blocks = _Blocks({"Door unit - 40": _Definition([a, FakeEntity(doc, "AcDbLine"), b])})
    out = block_editor.lock_attribute_positions("Door unit - 40")
    assert out == {"block": "Door unit - 40", "locked": ["MARK"], "already_locked": ["SIZE"]} and a.LockPosition
    assert doc.undo_log[-2:] == ["start", "end"]
    doc.variables["BLOCKEDITOR"] = 1
    with pytest.raises(AcadError, match="is open"):
        block_editor.lock_attribute_positions("Door unit - 40")


def test_check_dynamic_block_measures_each_case_and_cleans_up(fake_app, monkeypatch):
    doc, _ = _editor(fake_app, monkeypatch)
    doc.Blocks = _Blocks({"WAG-FAST-TEK-SIDE": _Definition([])})
    out = block_editor.check_dynamic_block("WAG-FAST-TEK-SIDE", [
        {"properties": {"Length": 2.0}, "expect": {"height": 1.0, "min_y": -1.0, "max_y": 0}},
        {"properties": {"Size": "#8-18"}, "expect": {"width": 0.5}},  # wrong on purpose
    ])
    first, second = out["cases"]
    assert first["passed"] and not second["passed"] and not out["passed"]
    assert second["misses"]["width"]["measured"] == round(0.348 - 0.432, 6)
    assert doc.space.items == []  # the temporary reference is gone
    with pytest.raises(ValueError):
        block_editor.check_dynamic_block("WAG-FAST-TEK-SIDE", [{"properties": {}, "expect": {"depth": 1}}])


# ---------- template tools: styles, page setup, attribute definitions, sheets ----------


def test_dimension_look_variables_are_allowed(fake_app):
    session.mark_owned(fake_app.doc)
    out = settings.set_drawing_variables({"DIMTAD": 1, "DIMTIH": 0, "dimfrac": 2, "DIMGAP": 0.0625})
    assert (out["DIMTAD"], out["DIMTIH"], out["DIMFRAC"]) == (1, 0, 2)
    assert out["dimension_style_updated"] == "Standard"
    with pytest.raises(AcadError, match="between"):
        settings.set_drawing_variables({"DIMTAD": 7})


def test_text_style_is_created_then_updated(fake_app):
    with pytest.raises(AcadError, match="locked"):
        settings.add_text_style("GD-NOTES")
    session.mark_owned(fake_app.doc)
    made = settings.add_text_style("GD-NOTES", font="romans.shx", width_factor=0.9, make_current=True)
    assert made["created"] and made["current"] and (made["font"], made["width_factor"]) == ("romans.shx", 0.9)
    assert fake_app.doc.ActiveTextStyle.Name == "GD-NOTES"
    again = settings.add_text_style("gd-notes", font="simplex.shx", oblique_angle=15)
    assert not again["created"] and again["font"] == "simplex.shx" and again["oblique_angle"] == pytest.approx(15)
    assert [s.Name for s in fake_app.doc.TextStyles.items].count("GD-NOTES") == 1
    with pytest.raises(AcadError, match="font file"):
        settings.add_text_style("X", font="Arial")
    with pytest.raises(AcadError, match="not a usable text style name"):
        settings.add_text_style("A/B")


def test_truetype_font_by_name_becomes_its_full_path(fake_app, monkeypatch, tmp_path):
    # AutoCAD took romans.shx by name but refused arial.ttf; the full path worked (live 2026-11-10).
    session.mark_owned(fake_app.doc)
    fonts = tmp_path / "Fonts"
    fonts.mkdir()
    (fonts / "arial.ttf").write_bytes(b"")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nowhere"))
    assert settings.add_text_style("GD-ARIAL", font="arial.ttf")["font"] == str(fonts / "arial.ttf")
    assert settings.add_text_style("GD-ARIAL", font=r"D:\fonts\mine.ttf")["font"] == r"D:\fonts\mine.ttf"
    with pytest.raises(AcadError, match="No font file 'nope.ttf'"):
        settings.add_text_style("X", font="nope.ttf")


def test_a_refused_font_file_gets_a_plain_message_and_no_style(fake_app):
    session.mark_owned(fake_app.doc)
    deleted = []

    class _Refusing:
        Name = "X"

        def __setattr__(self, key, value):
            raise AttributeError("Property 'Add.FontFile' can not be set.")

        def Delete(self):  # noqa: N802
            deleted.append(True)
    fake_app.doc.TextStyles.Add = lambda name: _Refusing()
    with pytest.raises(AcadError, match="did not accept the font file 'weird.shx'"):
        settings.add_text_style("X", font="weird.shx")
    assert deleted == [True]


def test_failed_text_style_change_is_put_back(fake_app):
    session.mark_owned(fake_app.doc)

    def refuse(which):
        raise RuntimeError("AutoCAD refused")
    fake_app.doc.Regen = refuse
    with pytest.raises(RuntimeError):
        settings.add_text_style("NOTES-TEXT", font="simplex.shx", height=0.125, make_current=True)
    style = fake_app.doc.TextStyles.Item(1)
    assert (style.FontFile, style.Height) == ("txt.shx", 0.0)
    assert fake_app.doc.ActiveTextStyle.Name == "Standard"


def test_dimension_style_copies_the_current_settings_and_becomes_current(fake_app):
    session.mark_owned(fake_app.doc)
    settings.add_text_style("GD-NOTES")
    out = settings.add_dimension_style("GD-3IN", {"dimscale": 4, "DIMTAD": 1, "DIMFRAC": 2},
                                       text_style="gd-notes", arrowhead="tick")
    style = fake_app.doc.ActiveDimStyle
    assert out["created"] and out["current"] and style.Name == "GD-3IN"
    copied = style.copied
    assert (copied["DIMSCALE"], copied["DIMTXSTY"], copied["DIMBLK"]) == (4.0, "GD-NOTES", "_ARCHTICK")
    assert out["settings"]["DIMTAD"] == 1
    with pytest.raises(AcadError, match="arrowhead must be"):
        settings.add_dimension_style("X", arrowhead="star")
    with pytest.raises(AcadError, match="not a dimension setting"):
        settings.add_dimension_style("X", {"LTSCALE": 2})
    with pytest.raises(AcadError, match="The drawing has"):
        settings.add_dimension_style("X", text_style="NOPE")
    assert [s.Name for s in fake_app.doc.DimStyles.items] == ["Standard", "ARCH-DIM", "GD-3IN"]


def test_existing_dimension_style_is_made_current_changed_and_its_dimensions_rebuilt(fake_app):
    session.mark_owned(fake_app.doc)
    updates = []
    dim = fake_app.doc.space._add(FakeEntity(fake_app.doc, "AcDbRotatedDimension", StyleName="ARCH-DIM"))
    dim.Update = lambda: updates.append("dim")
    out = settings.add_dimension_style("arch-dim", {"DIMSCALE": 48})
    style = fake_app.doc.ActiveDimStyle
    assert not out["created"] and style.Name == "ARCH-DIM" and style.copied["DIMSCALE"] == 48.0
    assert out["dimensions_rebuilt"] == 1 and updates == ["dim"]


def test_failed_dimension_style_leaves_no_style_and_no_changed_setting(fake_app):
    session.mark_owned(fake_app.doc)
    fake_app.doc.variables["DIMSCALE"] = 1.0
    with pytest.raises(RuntimeError):
        settings.add_dimension_style("NEW", {"DIMSCALE": 8, "DIMGAP": -999})  # the fake refuses -999
    assert fake_app.doc.variables["DIMSCALE"] == 1.0 and fake_app.doc.ActiveDimStyle.Name == "Standard"
    assert [s.Name for s in fake_app.doc.DimStyles.items] == ["Standard", "ARCH-DIM"]


def test_multileader_style_takes_the_plot_scale(fake_app):
    session.mark_owned(fake_app.doc)
    out = settings.add_multileader_style("GD-NOTES-3IN", scale=4, text_height=0.09375, text_style="notes-text")
    assert out == {"name": "GD-NOTES-3IN", "created": True, "scale": 4.0, "text_height": 0.09375,
                   "arrow_size": 0.18, "text_style": "NOTES-TEXT", "current": True}
    assert fake_app.doc.variables["CMLEADERSTYLE"] == "GD-NOTES-3IN"
    changed = settings.add_multileader_style("notes", scale=48, make_current=False)
    assert (changed["name"], changed["created"], changed["scale"], changed["current"]) == ("NOTES", False, 48.0, False)
    with pytest.raises(AcadError, match="scale must be positive"):
        settings.add_multileader_style("X", scale=0)
    with pytest.raises(AcadError, match="The drawing has"):
        settings.add_multileader_style("Y", text_style="NOPE")
    names = [s.Name for s in fake_app.doc.Dictionaries.Item("ACAD_MLEADERSTYLE").items]
    assert names == ["Standard", "NOTES", "GD-NOTES-3IN"]  # the failed one was removed again


def test_new_multileader_style_gets_a_text_style(fake_app):
    # A style made over COM has no text style, and reading it failed (live 2026-11-11).
    session.mark_owned(fake_app.doc)
    assert settings.add_multileader_style("PLAIN", scale=2)["text_style"] == "Standard"  # the current style's
    styles = fake_app.doc.Dictionaries.Item("ACAD_MLEADERSTYLE")
    styles.items[0]._text_style = None  # now the current multileader style has none either
    fake_app.doc.variables["CMLEADERSTYLE"] = "Standard"
    fake_app.doc.ActiveTextStyle = fake_app.doc.TextStyles.Item(1)
    assert settings.add_multileader_style("PLAIN-2")["text_style"] == "NOTES-TEXT"  # the current text style
    changed = settings.add_multileader_style("standard", scale=3, make_current=False)  # still without one
    assert changed["text_style"] == "" and changed["scale"] == 3.0


def test_add_layer_sets_the_plot_flag_only_when_asked(fake_app):
    session.mark_owned(fake_app.doc)
    assert layers.add_layer("S-ANNO-NPLT", color=9, plot=False)["plottable"] is False
    assert layers.add_layer("S-ANNO-NPLT", color=9)["plottable"] is False  # left as it is
    assert layers.add_layer("S-ANNO-NPLT", color=9, plot=True)["plottable"] is True


def test_page_setup_takes_the_best_pdf_driver_unless_one_is_named(fake_app, monkeypatch):
    # The legacy driver writes 600 dpi vectors; High Quality Print 2400 (measured live 2026-11-12).
    session.mark_owned(fake_app.doc)
    sheet = fake_app.doc.Layouts.Item(0)
    names = ("None", "Microsoft Print to PDF", "AutoCAD PDF (General Documentation).pc3",
             "AutoCAD PDF (High Quality Print).pc3", "DWG To PDF.pc3")
    monkeypatch.setattr(type(sheet), "GetPlotDeviceNames", lambda self: names)
    paper = "ANSI full bleed B (17.00 x 11.00 Inches)"
    assert sheets.set_page_setup("Sheet1", paper)["device"] == "AutoCAD PDF (High Quality Print).pc3"
    assert sheets.set_page_setup("Sheet1", paper, plot_device="general documentation")["device"] == \
        "AutoCAD PDF (General Documentation).pc3"
    assert sheets.set_page_setup("Sheet1", paper, device="DWG To PDF.pc3")["device"] == "DWG To PDF.pc3"  # old name
    with pytest.raises(AcadError, match="No plot device matches 'plotter'"):
        sheets.set_page_setup("Sheet1", paper, plot_device="plotter")
    assert plot.best_pdf_device(["None", "DWG To PDF.pc3"]) == "DWG To PDF.pc3"
    assert plot.best_pdf_device([]) == "DWG To PDF.pc3"
    assert plot.is_pdf_device("AutoCAD PDF (Smallest File).pc3") and plot.is_pdf_device("dwg to pdf.pc3")
    assert not plot.is_pdf_device("Microsoft Print to PDF") and not plot.is_pdf_device("None")


def test_page_setup_picks_one_paper_and_plots_the_layout_at_full_size(fake_app):
    session.mark_owned(fake_app.doc)
    sheet = fake_app.doc.Layouts.Item(0)
    out = sheets.set_page_setup("sheet1", "ANSI full bleed B (17.00 x 11.00 Inches)", plot_style="monochrome.ctb")
    assert out == {"layout": "Sheet1", "device": "DWG To PDF.pc3",
                   "paper": "ANSI_full_bleed_B_(17.00_x_11.00_Inches)",
                   "paper_name": "ANSI full bleed B (17.00 x 11.00 Inches)", "plot_style": "monochrome.ctb",
                   "plot_area": "layout", "scale": "1:1"}
    assert (sheet.PlotType, sheet.PlotRotation, sheet.UseStandardScale, sheet.StandardScale) == (5, 0, True, 16)
    assert sheets.set_page_setup("Sheet1", "ansi_a_(11.00_x_8.50_inches)")["paper_name"].startswith("ANSI A")
    with pytest.raises(AcadError, match="matches several paper sizes: ANSI B .17.00 x 11.00 Inches.; ANSI full"):
        sheets.set_page_setup("Sheet1", "17.00 x 11.00")
    with pytest.raises(AcadError, match="No plot style table matches 'company.ctb'"):
        sheets.set_page_setup("Sheet1", "ANSI B (17.00 x 11.00 Inches)", plot_style="company.ctb")
    assert sheet.CanonicalMediaName == "ANSI_A_(11.00_x_8.50_Inches)"  # both failures put the paper back
    assert sheet.StyleSheet == "monochrome.ctb"  # an empty plot_style keeps the table
    with pytest.raises(AcadError, match="not Model"):
        sheets.set_page_setup("Model", "ANSI A")


def test_failed_page_setup_on_a_layout_never_set_up_rolls_back_cleanly(fake_app):
    # Such a layout has no paper name, and AutoCAD refuses to be given "" again (live 2026-11-11).
    session.mark_owned(fake_app.doc)
    sheet = fake_app.doc.Layouts.Item(0)
    sheet._media = ""
    with pytest.raises(AcadError, match="matches several paper sizes") as err:
        sheets.set_page_setup("Sheet1", "17.00 x 11.00")
    assert "rollback was incomplete" not in str(err.value)
    assert (sheet.ConfigName, sheet.PlotRotation) == ("None", 1)


def test_page_setup_refuses_a_user_drawing(fake_app):
    with pytest.raises(AcadError, match="locked"):
        sheets.set_page_setup("Sheet1", "ANSI A")
    assert fake_app.doc.Layouts.Item(0).ConfigName == "None"


def test_insert_block_on_a_sheet_goes_to_its_paper_space(fake_app):
    session.mark_owned(fake_app.doc)

    class _Blocks:
        def Item(self, name):  # noqa: N802
            return name
    fake_app.doc.Blocks = _Blocks()
    info = blocks.insert_block("GD-TITLE-B", [0, 0], layout="sheet1")
    assert info["layout"] == "Sheet1"
    assert [e.Handle for e in fake_app.doc.paper.items] == [info["handle"]] and fake_app.doc.space.items == []
    assert "layout" not in blocks.insert_block("GD-TITLE-B", [0, 0])  # model space, as before
    with pytest.raises(AcadError, match="No layout named"):
        blocks.insert_block("GD-TITLE-B", [0, 0], layout="A-101")


def test_attribute_definition_modes_and_checks(fake_app):
    session.mark_owned(fake_app.doc)
    info = blocks.add_attribute_definition("sheet", [1, 2], 0.125, prompt="Sheet number", default="S-501")
    att = fake_app.doc.HandleToObject(info["handle"])
    assert (info["tag"], info["prompt"], info["default"]) == ("SHEET", "Sheet number", "S-501")
    assert att.Mode == 16 and att.InsertionPoint == (1, 2, 0)  # position locked by default
    hidden = blocks.add_attribute_definition("REV", [1, 1], 0.125, invisible=True, lock_position=False)
    assert fake_app.doc.HandleToObject(hidden["handle"]).Mode == 1 and hidden["prompt"] == "REV"
    with pytest.raises(AcadError, match="without spaces"):
        blocks.add_attribute_definition("SHEET NO", [0, 0], 0.125)
    with pytest.raises(AcadError, match="height must be positive"):
        blocks.add_attribute_definition("DATE", [0, 0], 0)
    with pytest.raises(AcadError, match="No layer named"):
        blocks.add_attribute_definition("DATE", [0, 0], 0.125, layer="NOPE")
    assert fake_app.doc.ModelSpace.Count == 2  # the one on a missing layer was removed again


# ---------- block definitions: define_block, import_blocks ----------


class _Item:
    """An object inside a fake block definition or space."""

    _handles = 0x9000

    def __init__(self, owner, object_name="AcDbLine", **props):
        _Item._handles += 1
        self.Handle, self.ObjectName, self.owner = f"{_Item._handles:X}", object_name, owner
        self.__dict__.update(props)

    @property
    def OwnerID(self):  # noqa: N802
        return self.owner.ObjectID

    def Delete(self):  # noqa: N802
        self.owner.items.remove(self)

    def clone(self, owner):
        props = {k: v for k, v in self.__dict__.items() if k not in ("Handle", "ObjectName", "owner")}
        return _Item(owner, self.ObjectName, **props)


class _Ref(_Item):
    """A block reference: follows its definition by identity (so a renamed definition keeps it), and a
    dynamic one is drawn by an anonymous copy."""

    def __init__(self, owner, definition, **props):
        super().__init__(owner, "AcDbBlockReference", **props)
        self.definition = definition
        self.props = [FakeDynProp(n, v, allowed) for n, (v, allowed) in definition.dynamic.items()]

    @property
    def EffectiveName(self):  # noqa: N802
        return self.definition.Name

    @property
    def IsDynamicBlock(self):  # noqa: N802
        return bool(self.definition.dynamic)

    @property
    def Name(self):  # noqa: N802
        return "*U7" if self.definition.dynamic else self.definition.Name

    @Name.setter
    def Name(self, value):  # noqa: N802
        self.definition = self.owner.table.Item(value)  # refused unless that definition exists
        self.props = [FakeDynProp(n, v, allowed) for n, (v, allowed) in self.definition.dynamic.items()]

    def GetDynamicBlockProperties(self):  # noqa: N802
        return list(self.props)

    def clone(self, owner):
        return _Ref(owner, owner.table.Item(self.definition.Name))


class _Def:
    _ids = 500

    def __init__(self, table, name, origin=(0.0, 0.0, 0.0), layout=False, dynamic=None):
        _Def._ids += 1
        self.ObjectID, self.table, self.Name, self.Origin = _Def._ids, table, name, tuple(origin)
        self.IsLayout, self.IsXRef, self.dynamic, self.items = layout, False, dict(dynamic or {}), []

    @property
    def IsDynamicBlock(self):  # noqa: N802
        return bool(self.dynamic)

    @property
    def Origin(self):  # noqa: N802 - read back as a tuple, set with a VARIANT, as over COM
        return self._origin

    @Origin.setter
    def Origin(self, value):  # noqa: N802
        self._origin = tuple(float(v) for v in _xyz_of(value))

    @property
    def Count(self):  # noqa: N802
        return len(self.items)

    def Item(self, i):  # noqa: N802
        return self.items[i]

    def add(self, item):
        self.items.append(item)
        return item

    def Delete(self):  # noqa: N802
        if any(isinstance(i, _Ref) and i.definition is self for d in self.table.defs for i in d.items):
            raise _com_error(-2145386420)  # still referenced
        self.table.defs.remove(self)

    def InsertBlock(self, insertion, name, xs, ys, zs, rotation):  # noqa: N802
        return self.add(_Ref(self, self.table.Item(name), InsertionPoint=_xyz_of(insertion)))


def _xyz_of(variant):
    return tuple(getattr(variant, "value", variant))


class _Table:
    """A drawing's Blocks collection plus its CopyObjects (deep cloning, like AutoCAD's)."""

    def __init__(self):
        self.defs = []
        self.model = self.new("*Model_Space", layout=True)
        self.copies = 0
        self.fail_copy = False

    def new(self, name, **kw):
        definition = _Def(self, name, **kw)
        self.defs.append(definition)
        return definition

    @property
    def Count(self):  # noqa: N802
        return len(self.defs)

    def Item(self, key):  # noqa: N802
        if isinstance(key, int):
            return self.defs[key]
        for d in self.defs:
            if d.Name.lower() == str(key).lower():
                return d
        raise _com_error(-2145386476)

    def Add(self, origin, name):  # noqa: N802
        if any(d.Name.lower() == name.lower() for d in self.defs):
            raise _com_error(-2145386476)
        return self.new(name, origin=_xyz_of(origin))

    def CopyObjects(self, objs, owner):  # noqa: N802
        self.copies += 1
        if self.fail_copy:
            raise _com_error(-2147467259)
        items = list(objs.value)
        if isinstance(owner, _Table):  # whole definitions, nested ones first, same names mapped to existing
            def clone(definition):
                try:
                    return owner.Item(definition.Name)
                except pywintypes.com_error:
                    pass
                for i in definition.items:
                    if isinstance(i, _Ref):
                        clone(i.definition)
                copy = owner.new(definition.Name, origin=definition.Origin, dynamic=definition.dynamic)
                copy.items = [i.clone(copy) for i in definition.items]
                return copy
            return tuple(clone(d) for d in items)
        copies = tuple(owner.add(i.clone(owner) if hasattr(i, "clone") else _Item(owner, i.ObjectName))
                       for i in items)
        return copies, ()  # late binding hands back the IDPairs output too (live 2026-11-18)


def _library_drawing(fake_app, monkeypatch, tmp_path):
    """The drawing being built (owned, Blocks faked) and a library file read through ObjectDBX."""
    doc = fake_app.doc
    session.mark_owned(doc)
    doc.Blocks = _Table()
    doc.CopyObjects = doc.Blocks.CopyObjects
    doc.variables["BLOCKEDITOR"] = 0
    path = tmp_path / "Library.dwg"
    path.write_bytes(b"")

    class _Dbx:
        Blocks = _Table()
        opened = None

        def Open(self, p):  # noqa: N802
            self.opened = p

        def CopyObjects(self, objs, owner):  # noqa: N802
            return self.Blocks.CopyObjects(objs, owner)
    dbx = _Dbx()
    progids = []
    fake_app.GetInterfaceObject = lambda progid: progids.append(progid) or dbx
    return doc, dbx, str(path), progids


def _model_items(fake_app, doc):
    """define_block's objects live in the fake model space (FakeSpace), which needs an ObjectID."""
    doc.space.ObjectID = 11
    a = doc.space.AddLine(com.point([0, 0]), com.point([10, 0]))
    b = doc.space.AddCircle(com.point([5, 5]), 2.0)
    for ent in (a, b):
        ent.OwnerID = 11
    return a, b


def test_define_block_copies_objects_into_a_new_definition(fake_app, monkeypatch, tmp_path):
    doc, _, _, _ = _library_drawing(fake_app, monkeypatch, tmp_path)
    a, b = _model_items(fake_app, doc)
    c = doc.space.AddLine(com.point([0, 1]), com.point([10, 1]))
    c.OwnerID = 11
    out = block_library.define_block("Door tag", [a.Handle, b.Handle, c.Handle], [5, 0])
    made = doc.Blocks.Item("Door tag")
    assert out == {"block": "Door tag", "base_point": [5.0, 0.0, 0.0], "objects": 3, "redefined": False,
                   "originals": "keep"}  # counted in the definition, not from CopyObjects' pair (live 2026-11-18)
    assert made.Origin == (5.0, 0.0, 0.0) and [i.ObjectName for i in made.items] == ["AcDbLine", "AcDbCircle",
                                                                                    "AcDbLine"]
    assert a in doc.space.items and doc.undo_log[-2:] == ["start", "end"]  # kept; one undo step


def test_define_block_refuses_what_it_should(fake_app, monkeypatch, tmp_path):
    doc, _, _, _ = _library_drawing(fake_app, monkeypatch, tmp_path)
    a, b = _model_items(fake_app, doc)
    doc.Blocks.new("Door tag")
    with pytest.raises(AcadError, match="already exists.*redefine=True"):
        block_library.define_block("Door tag", [a.Handle], [0, 0])
    doc.Blocks.new("Window", dynamic={"Width": (36.0, ())})
    with pytest.raises(AcadError, match="dynamic block.*import_blocks"):
        block_library.define_block("Window", [a.Handle], [0, 0], redefine=True)
    b.OwnerID = 12
    with pytest.raises(AcadError, match="different spaces"):
        block_library.define_block("New", [a.Handle, b.Handle], [0, 0])
    for bad in ["", " lead", "a/b", "x" * 256]:
        with pytest.raises(ValueError, match="not a usable block name"):
            block_library.define_block(bad, [a.Handle], [0, 0])
    with pytest.raises(ValueError, match="originals"):
        block_library.define_block("New", [a.Handle], [0, 0], originals="explode")
    doc.variables["BLOCKEDITOR"] = 1
    with pytest.raises(AcadError, match="Block Editor is open"):
        block_library.define_block("New", [a.Handle], [0, 0])
    doc.variables["BLOCKEDITOR"] = 0
    fake_app.doc.variables["CMDACTIVE"] = 1
    with pytest.raises(AcadError, match="busy"):
        block_library.define_block("New", [a.Handle], [0, 0])
    assert [d.Name for d in doc.Blocks.defs] == ["*Model_Space", "Door tag", "Window"]


def test_define_block_redefines_and_puts_the_old_contents_back_on_failure(fake_app, monkeypatch, tmp_path):
    doc, _, _, _ = _library_drawing(fake_app, monkeypatch, tmp_path)
    a, b = _model_items(fake_app, doc)
    old = doc.Blocks.new("Door tag", origin=(1.0, 1.0, 0.0))
    old.add(_Item(old, "AcDbArc"))
    real_copy = doc.Blocks.CopyObjects

    def fail_on_the_new_contents(objs, owner):
        if owner is old and any(o is a for o in objs.value):
            raise _com_error(-2147467259)
        return real_copy(objs, owner)
    doc.CopyObjects = fail_on_the_new_contents
    with pytest.raises(pywintypes.com_error):  # through MCP it becomes a ToolError
        block_library.define_block("Door tag", [a.Handle], [5, 0], redefine=True)
    assert [i.ObjectName for i in old.items] == ["AcDbArc"] and old.Origin == (1.0, 1.0, 0.0)
    assert [d.Name for d in doc.Blocks.defs] == ["*Model_Space", "Door tag"]  # no backup left behind
    doc.CopyObjects = real_copy
    out = block_library.define_block("Door tag", [a.Handle, b.Handle], [5, 0], redefine=True)
    assert out["redefined"] and [i.ObjectName for i in old.items] == ["AcDbLine", "AcDbCircle"]
    assert old.Origin == (5.0, 0.0, 0.0) and "regen" in doc.undo_log
    assert [d.Name for d in doc.Blocks.defs] == ["*Model_Space", "Door tag"]


def test_define_block_can_replace_the_originals_with_a_reference(fake_app, monkeypatch, tmp_path):
    doc, _, _, _ = _library_drawing(fake_app, monkeypatch, tmp_path)
    a, b = _model_items(fake_app, doc)
    out = block_library.define_block("Door tag", f"{a.Handle}, {b.Handle}", [5, 0], originals="replace")
    assert a not in doc.space.items and b not in doc.space.items
    ref = doc.HandleToObject(out["reference"])
    assert ref.InsertionPoint == (5.0, 0.0, 0.0) and ref.EffectiveName == "Door tag"


def _library(dbx):
    """The library file: a dynamic Window (with a nested Sash), a Tag, and Title."""
    lib = dbx.Blocks
    sash = lib.new("Sash")
    sash.add(_Item(sash))
    window = lib.new("Window", dynamic={"Width": (36.0, (24.0, 36.0, 48.0)), "Swing": ("Left", ("Left", "Right"))})
    window.add(_Item(window, "AcDbPolyline"))
    window.add(_Ref(window, sash))
    tag = lib.new("Tag")
    tag.add(_Item(tag, "AcDbAttributeDefinition", TagString="MARK"))
    lib.new("Title")
    return lib


def test_import_blocks_brings_new_definitions_in_whole_and_skips_existing(fake_app, monkeypatch, tmp_path):
    doc, dbx, path, progids = _library_drawing(fake_app, monkeypatch, tmp_path)
    _library(dbx)
    doc.Blocks.new("Tag")  # already in the drawing
    out = block_library.import_blocks(path, ["window", "Tag"])
    assert progids == ["ObjectDBX.AxDbDocument.26"] and dbx.opened == path  # read, not opened as a tab
    assert out["imported"] == ["Window"] and out["skipped_existing"] == ["Tag"] and out["replaced"] == []
    assert out["nested_brought_in"] == ["sash"]
    window = doc.Blocks.Item("Window")
    assert window.dynamic and [i.ObjectName for i in window.items] == ["AcDbPolyline", "AcDbBlockReference"]
    assert doc.Blocks.Item("Tag").items == []  # left as it was
    every = block_library.import_blocks(path)
    assert every["imported"] == ["Title"] and set(every["skipped_existing"]) == {"Sash", "Window", "Tag"}


def test_import_blocks_overwrite_switches_every_reference_and_keeps_its_values(fake_app, monkeypatch, tmp_path):
    doc, dbx, path, _ = _library_drawing(fake_app, monkeypatch, tmp_path)
    _library(dbx)
    old = doc.Blocks.new("Window", dynamic={"Width": (36.0, (24.0, 36.0)), "Swing": ("Left", ("Left", "Right")),
                                            "Mullions": (1.0, ())})
    old.add(_Item(old, "AcDbLine"))
    placed = doc.Blocks.model.add(_Ref(doc.Blocks.model, old, InsertionPoint=(10, 20, 0)))
    placed.props[0].Value, placed.props[1].Value = 24.0, "Right"
    legend = doc.Blocks.new("Legend")
    nested = legend.add(_Ref(legend, old))
    nested.props[2].Value = 3.0
    out = block_library.import_blocks(path, ["Window"], overwrite=True)
    new = doc.Blocks.Item("Window")
    assert out["replaced"] == ["Window"] and out["imported"] == [] and out["references_switched"] == 2
    assert new is not old and placed.definition is new and nested.definition is new
    assert placed.InsertionPoint == (10, 20, 0)
    assert {p.PropertyName: p.Value for p in placed.props} == {"Width": 24.0, "Swing": "Right"}
    assert out["values_not_restored"] == {h: ["Mullions"] for h in (placed.Handle, nested.Handle)}  # gone in the new
    assert old not in doc.Blocks.defs and "old_definitions_left" not in out  # the old definition is gone
    assert "regen" in doc.undo_log


def test_import_blocks_puts_everything_back_when_it_fails(fake_app, monkeypatch, tmp_path):
    doc, dbx, path, _ = _library_drawing(fake_app, monkeypatch, tmp_path)
    _library(dbx)
    old = doc.Blocks.new("Window", dynamic={"Width": (36.0, (24.0, 36.0))})
    placed = doc.Blocks.model.add(_Ref(doc.Blocks.model, old))
    placed.props[0].Value = 24.0

    def regen_fails(which):
        raise _com_error(-2147467259)
    doc.Regen = regen_fails
    with pytest.raises(pywintypes.com_error):
        block_library.import_blocks(path, ["Window"], overwrite=True)
    assert old.Name == "Window" and doc.Blocks.Item("Window") is old and placed.definition is old
    assert placed.props[0].Value == 24.0
    assert [d.Name for d in doc.Blocks.defs] == ["*Model_Space", "Window"]  # copies and nested Sash removed


def test_import_blocks_checks_before_touching_anything(fake_app, monkeypatch, tmp_path):
    doc, dbx, path, progids = _library_drawing(fake_app, monkeypatch, tmp_path)
    _library(dbx)
    with pytest.raises(AcadError, match="no block 'Door'.*It has: Sash, Tag, Title, Window"):
        block_library.import_blocks(path, ["Door"])
    with pytest.raises(AcadError, match="Not found or not a drawing"):
        block_library.import_blocks(str(tmp_path / "missing.dwg"))
    with pytest.raises(AcadError, match="Not found or not a drawing"):
        block_library.import_blocks(str(tmp_path))
    session.owned.clear()
    with pytest.raises(AcadError, match="locked"):
        block_library.import_blocks(path)
    assert dbx.Blocks.copies == 0 and [d.Name for d in doc.Blocks.defs] == ["*Model_Space"]


def test_import_blocks_reads_an_open_library_from_autocad(fake_app, monkeypatch, tmp_path):
    doc, dbx, path, progids = _library_drawing(fake_app, monkeypatch, tmp_path)
    opened = FakeDoc("Library.dwg", path)
    opened.Blocks = _Table()
    opened.Blocks.new("Title")
    opened.CopyObjects = opened.Blocks.CopyObjects
    fake_app.Documents.docs.append(opened)
    out = block_library.import_blocks(path)
    assert out["imported"] == ["Title"] and out["source"] == "'Library.dwg' (open in AutoCAD)" and progids == []


# ---------- text justification and style (T5) ----------


@pytest.fixture()
def text_enums(monkeypatch):
    names = ["Left", "Center", "Right", "Aligned", "Middle", "Fit", "TopLeft", "TopCenter", "TopRight", "MiddleLeft",
             "MiddleCenter", "MiddleRight", "BottomLeft", "BottomCenter", "BottomRight"]
    values = {f"acAlignment{n}": i for i, n in enumerate(names)}
    corners = ["TopLeft", "TopCenter", "TopRight", "MiddleLeft", "MiddleCenter", "MiddleRight", "BottomLeft",
               "BottomCenter", "BottomRight"]
    values.update({f"acAttachmentPoint{n}": i for i, n in enumerate(corners, start=1)})
    monkeypatch.setattr(com.enums, "_values", {**com.enums._values, **values})


def test_add_text_centres_on_the_point_in_the_style_asked_for(fake_app, text_enums):
    session.mark_owned(fake_app.doc)
    out = draw.add_text("BATH", [5, 5], 0.125, justify="MC", style="notes-text")
    ent = fake_app.doc.HandleToObject(out["handle"])
    assert ent.Alignment == 10 and ent.TextAlignmentPoint == (5.0, 5.0, 0.0)
    assert ent.StyleName == "NOTES-TEXT" and out["style"] == "NOTES-TEXT"
    assert out["justify"] == "middle_center" and out["justification_point"] == [5.0, 5.0, 0.0]
    plain = draw.add_text("NOTE", [0, 0], 0.125)
    assert plain["justify"] == "left" and fake_app.doc.HandleToObject(plain["handle"]).Alignment == 0
    assert draw.add_text("R", [1, 1], 0.1, justify="Bottom Right")["justify"] == "bottom_right"


def test_add_text_refuses_unknown_justification_and_style_and_leaves_nothing(fake_app, text_enums):
    session.mark_owned(fake_app.doc)
    with pytest.raises(AcadError, match="justify is one of left, center"):
        draw.add_text("X", [0, 0], 0.1, justify="fit")  # fit and aligned need two points: not offered
    with pytest.raises(AcadError, match="No text style named 'ROMANS'.*Standard, NOTES-TEXT"):
        draw.add_text("X", [0, 0], 0.1, style="ROMANS")
    assert fake_app.doc.ModelSpace.Count == 0


def test_add_mtext_attachment_and_style(fake_app, text_enums):
    session.mark_owned(fake_app.doc)
    out = draw.add_mtext(r"LIVING\PROOM", [10, 4], 3, attachment="middle_center", style="NOTES-TEXT")
    ent = fake_app.doc.HandleToObject(out["handle"])
    assert ent.AttachmentPoint == 5 and ent.InsertionPoint == (10.0, 4.0, 0.0)
    assert out["attachment"] == "middle_center" and ent.StyleName == "NOTES-TEXT"
    assert draw.add_mtext("A", [0, 0], 1)["attachment"] == "top_left"
    with pytest.raises(AcadError, match="attachment is one of"):
        draw.add_mtext("A", [0, 0], 1, attachment="middle")


def test_attribute_definition_can_be_centred_in_a_style(fake_app, text_enums):
    session.mark_owned(fake_app.doc)
    info = blocks.add_attribute_definition("MARK", [2, 3], 0.1, justify="middle_center", style="NOTES-TEXT")
    att = fake_app.doc.HandleToObject(info["handle"])
    assert att.Alignment == 10 and att.TextAlignmentPoint == (2.0, 3.0, 0.0)
    assert info["style"] == "NOTES-TEXT" and info["justify"] == "middle_center"


# ---------- which space the drawing tools use (B6) ----------


def test_draw_tools_say_which_space_and_warn_when_a_sheet_is_active(fake_app):
    # B6: with a sheet tab active, draw_* still wrote to model space unnoticed, and the next -BLOCK said
    # "not in current space". Model space stays the default; the result now says so.
    doc = fake_app.doc
    session.mark_owned(doc)
    doc.ActiveLayout = doc.Layouts.Item(0)  # Sheet1, paper space current
    line = draw.draw_line([0, 0], [1, 0])
    assert line["space"] == "model" and "Sheet1" in line["note"] and "layout='Sheet1'" in line["note"]
    assert doc.HandleToObject(line["handle"]) in doc.space.items
    doc.MSpace = True  # working inside a viewport: model space is the current space
    assert "note" not in draw.draw_circle([0, 0], 1)
    doc.MSpace, doc.ActiveLayout = False, doc.Layouts.Item(1)  # the Model tab
    plain = draw.draw_line([0, 0], [2, 1])
    assert plain["space"] == "model" and "note" not in plain


def test_draw_tools_can_draw_on_a_sheet(fake_app, text_enums):
    doc = fake_app.doc
    session.mark_owned(doc)
    circle = draw.draw_circle([5, 5], 1, layout="sheet1")
    assert (circle["space"], circle["layout"]) == ("paper", "Sheet1") and "note" not in circle
    assert doc.HandleToObject(circle["handle"]) in doc.paper.items
    text = draw.add_text("A-101", [10, 1], 0.2, justify="BR", layout="Sheet1")
    assert text["space"] == "paper" and doc.HandleToObject(text["handle"]) in doc.paper.items
    att = blocks.add_attribute_definition("SHEET", [1, 1], 0.2, layout="Sheet1")
    assert att["space"] == "paper" and doc.HandleToObject(att["handle"]) in doc.paper.items
    centre = draw.draw_center_mark([0, 0], 1, layout="Sheet1")
    assert centre["space"] == "paper" and len(doc.paper.items) == 5
    assert draw.draw_line([0, 0], [1, 1], layout="Model")["space"] == "model"
    with pytest.raises(AcadError, match="No layout named 'A-101'.*Sheet1, Model"):
        draw.draw_line([0, 0], [1, 1], layout="A-101")


# ---------- Block Editor contents (T10), visibility (T6), flip, rotation and other actions (T8) ----------


def test_list_block_editor_objects_reads_the_editor_space(fake_app, monkeypatch):
    # T10, live 2026-11-18 (AMCP-LIVE-20261118-02/03): inside the Block Editor, COM's ModelSpace holds the
    # editor's objects (with new handles), parameters, grips and actions included.
    doc, _ = _editor(fake_app, monkeypatch, open_=True)
    circle = doc.space._add(FakeEntity(doc, "AcDbCircle"))
    param = doc.space._add(FakeEntity(doc, "AcDbBlockLinearParameterEntity"))
    doc.space._add(FakeEntity(doc, "AcDbBlockLinearGripEntity"))
    action = doc.space._add(FakeEntity(doc, "AcDbBlockMoveActionEntity"))
    out = block_authoring.list_block_editor_objects()
    assert out["geometry"] == [{"handle": circle.Handle, "type": "Circle", "layer": "0",
                                "bbox": [[0.0, 0.0], [1.0, 1.0]]}]
    assert out["parameters"] == [{"handle": param.Handle, "type": "LinearParameter"}]
    assert out["actions"] == [{"handle": action.Handle, "type": "MoveAction"}] and "grips" not in out
    assert [g["type"] for g in block_authoring.list_block_editor_objects(["grips"])["grips"]] == ["LinearGrip"]
    with pytest.raises(ValueError):
        block_authoring.list_block_editor_objects(["blocks"])
    doc.variables["BLOCKEDITOR"] = 0
    with pytest.raises(AcadError, match="not open"):
        block_authoring.list_block_editor_objects()


class _StateBlock:
    """A block with visibility states that -BVSTATE, BSAVE and BCLOSE act on like AutoCAD (T11):
    New appends (copying what the current state shows with _C), Delete refuses the current state."""

    def __init__(self, doc, monkeypatch, shows, extra=None, fail_on=None):
        self.doc, self.saved, self.extra, self.fail_on, self.calls = doc, dict(shows), extra or {}, fail_on, []
        self.editing, self.current = {}, None
        session.mark_owned(doc)
        doc.variables["BLOCKEDITOR"] = 0
        doc.Blocks = _Blocks({"Door unit - 40": _Definition([])})
        monkeypatch.setattr(block_editor.commands, "run", self.run)
        monkeypatch.setattr(doc.space, "InsertBlock", self.insert)

    def insert(self, insertion, block, xs, ys, zs, rotation):  # noqa: N802
        ref = FakeBlockRef(self.doc, block, (0.0, 0.0, 0.0))
        states = tuple(self.saved)
        ref.props = [FakeDynProp("Style", states[0], states), FakeDynProp("Width", 48.0, (48.0, 60.0))]
        ref.props += [FakeDynProp(n, v[0], v) for n, v in self.extra.items()]
        return self.doc.space._add(ref)

    def run(self, doc, command, inputs=(), undo_on_failure=True, timeout_seconds=30.0):
        self.calls.append((command, list(inputs)))
        ok = (command, list(inputs)) != self.fail_on
        if command == "-BEDIT":
            doc.variables["BLOCKEDITOR"], self.editing = 1, dict(self.saved)
            self.current = next(iter(self.editing))
        elif command == "BSAVE":
            self.saved = dict(self.editing)
        elif command == "BCLOSE":
            doc.variables["BLOCKEDITOR"] = 0
        elif command == "-BVSTATE" and ok:
            option, state = inputs[0], inputs[1]
            if option == "_S":
                ok = state in self.editing
                self.current = state if ok else self.current
            elif option == "_N":
                ok = state not in self.editing
                if ok:
                    self.editing[state], self.current = self.editing[self.current], state
            elif option == "_D":
                ok = state in self.editing and state != self.current
                if ok:
                    del self.editing[state]
        return {"completed": ok, "steps": [{"sent": command, "prompt": "x"}], "inputs_used": len(inputs),
                "cancelled": False, "undone": not ok, "problem": None if ok else "refused"}


def test_order_visibility_states_rebuilds_them_in_the_new_order(fake_app, monkeypatch):
    shows = {"VisibilityState0": {"frame"}, "24 in": {"frame", "leaf"}, "36 in": {"frame", "leaf", "glass"}}
    fake = _StateBlock(fake_app.doc, monkeypatch, shows)
    out = block_authoring.order_visibility_states("Door unit - 40", default="36 in")
    assert out["states"] == ["36 in", "VisibilityState0", "24 in"] and out["default"] == "36 in" and out["changed"]
    assert "problem" not in out and fake.saved == shows  # every state still shows what it showed
    assert list(fake.saved) == out["states"] and fake_app.doc.variables["BLOCKEDITOR"] == 0
    assert fake_app.doc.space.items == []  # both temporary copies are gone
    out = block_authoring.order_visibility_states("Door unit - 40", ["24 in", "36 IN", "visibilitystate0"])
    assert out["states"] == ["24 in", "36 in", "VisibilityState0"] and fake.saved == shows
    calls = len(fake.calls)
    assert not block_authoring.order_visibility_states("Door unit - 40", default="24 in")["changed"]
    assert len(fake.calls) == calls  # already first: nothing run


def test_order_visibility_states_leaves_the_block_alone_when_a_step_fails(fake_app, monkeypatch):
    shows = {"A": {"a"}, "B": {"b"}}
    fake = _StateBlock(fake_app.doc, monkeypatch, shows, fail_on=("-BVSTATE", ["_D", "A"]))
    with pytest.raises(AcadError, match="stopped: .*closed without saving, so the block is unchanged"):
        block_authoring.order_visibility_states("Door unit - 40", ["B", "A"])
    assert fake.saved == shows and list(fake.saved) == ["A", "B"] and fake_app.doc.variables["BLOCKEDITOR"] == 0
    assert ("BSAVE", []) not in fake.calls
    for bad, match in [(dict(states=["B"]), "every visibility state once"),
                       (dict(states=["A", "A"]), "every visibility state once"),
                       (dict(default="C"), "No visibility state 'C'")]:
        with pytest.raises(AcadError, match=match):
            block_authoring.order_visibility_states("Door unit - 40", **bad)
    with pytest.raises(ValueError, match="either states"):
        block_authoring.order_visibility_states("Door unit - 40", ["B", "A"], default="B")


def test_order_visibility_states_refuses_blocks_with_a_lookup(fake_app, monkeypatch):
    fake = _StateBlock(fake_app.doc, monkeypatch, {"A": set(), "B": set()}, extra={"Size": ("S", "L")})
    with pytest.raises(AcadError, match="more than one list property .*Style, Size"):
        block_authoring.order_visibility_states("Door unit - 40", default="B")
    assert fake.calls == []
    fake.extra = {}
    fake_app.doc.space._add(FakeEntity(fake_app.doc, "AcDbBlockLookupParameterEntity"))  # seen in the editor
    with pytest.raises(AcadError, match="has a lookup parameter"):
        block_authoring.order_visibility_states("Door unit - 40", default="B")
    assert [c[0] for c in fake.calls] == ["-BEDIT", "BCLOSE"] and list(fake.saved) == ["A", "B"]
    fake_app.doc.variables["BLOCKEDITOR"] = 1
    with pytest.raises(AcadError, match="is open"):
        block_authoring.order_visibility_states("Door unit - 40", default="B")
    session.owned.clear()
    fake_app.doc.variables["BLOCKEDITOR"] = 0
    with pytest.raises(AcadError, match="locked"):
        block_authoring.order_visibility_states("Door unit - 40", default="B")


def test_visibility_tools_follow_the_live_prompts(fake_app, monkeypatch):
    # T6, prompts recorded live 2026-11-18 (AMCP-LIVE-20261118-03).
    _, runs = _editor(fake_app, monkeypatch, open_=True)
    block_authoring.add_visibility_parameter([80, 90], "Size")
    block_authoring.visibility_state("new", "36 in")
    block_authoring.visibility_state("new", "48 in", new_state_shows="show_all")
    block_authoring.visibility_state("set", "36 in")
    block_authoring.visibility_state("delete", "48 in")
    block_authoring.set_object_visibility({"crossing": [[24, 36], [36, 48]]}, visible=False)
    block_authoring.set_object_visibility({"handles": ["8A"]}, visible=True, all_states=True)
    assert [(c, i) for c, i, _ in runs.calls] == [
        ("BPARAMETER", ["_V", "_L", "Size", [80, 90], "1"]),
        ("-BVSTATE", ["_N", "36 in", "_C"]),
        ("-BVSTATE", ["_N", "48 in", "_S"]),
        ("-BVSTATE", ["_S", "36 in"]),
        ("-BVSTATE", ["_D", "48 in"]),
        ("BVHIDE", [{"crossing": [[24, 36], [36, 48]]}, "", "_C"]),
        ("BVSHOW", [{"handles": ["8A"]}, "", "_A"]),
    ]
    for bad in [lambda: block_authoring.visibility_state("rename", "x"),
                lambda: block_authoring.visibility_state("new", " "),
                lambda: block_authoring.visibility_state("new", "x", new_state_shows="some"),
                lambda: block_authoring.add_visibility_parameter([0, 0], grips=2),
                lambda: block_authoring.set_object_visibility({"crossing": [[0, 0]]}, visible=True)]:
        with pytest.raises(ValueError):
            bad()
    assert len(runs.calls) == 7


def test_flip_and_rotation_parameters_follow_the_recorded_prompts(fake_app, monkeypatch):
    # T8: flip's Label also asks for the two values, rotation's for the label (live 2026-11-18, -03).
    _, runs = _editor(fake_app, monkeypatch, open_=True)
    flip = block_authoring.add_flip_parameter("Hinge side", [0, -12], [60, -12], [30, -16])
    turn = block_authoring.add_rotation_parameter("Angle", [30, 42], 10, [30, 56], value_list=[0, 90, 180])
    (_, flip_in, _), (_, turn_in, _) = runs.calls
    assert flip_in == ["_F", "_L", "Hinge side", "Not flipped", "Flipped", [0, -12], [60, -12], [30, -16], "1"]
    assert flip["pick_point"] == [15.0, -12.0]
    assert turn_in == ["_R", "_L", "Angle", "_V", "_L", "0,90,180", [30, 42], 10.0, 0.0, [30, 56], "1"]
    assert math.isclose(math.dist(turn["pick_point"], [30, 42]), 10, abs_tol=1e-5)
    for bad in [lambda: block_authoring.add_flip_parameter("F", [0, 0], [0, 0], [1, 1]),
                lambda: block_authoring.add_flip_parameter("F", [0, 0], [1, 0], [1, 1], grips=2),
                lambda: block_authoring.add_rotation_parameter("A", [0, 0], 0, [1, 1]),
                lambda: block_authoring.add_rotation_parameter("A", [0, 0], 1, [1, 1], grips=2)]:
        with pytest.raises(ValueError):
            bad()


def test_add_action_answers_per_kind(fake_app, monkeypatch):
    # T8: move and scale recorded live 2026-11-18 (-03); flip and rotate ask no action type.
    doc, runs = _editor(fake_app, monkeypatch, open_=True)
    fake_app.ZoomExtents = lambda: None
    doc.variables["BACTIONBARMODE"] = 1
    box = {"crossing": [[24, 36], [36, 48]]}
    block_authoring.add_action("move", [15, -6], box, offset=90, multiplier=0.5, location=[35, -20])
    block_authoring.add_action("scale", [15, -6], box, location=[20, -20])
    block_authoring.add_action("flip", [15, -12], {"handles": ["8A"]})
    block_authoring.add_action("rotate", [37, 49], box, location=[45, 50])
    assert [i for _, i, _ in runs.calls] == [
        [[15, -6], "_M", "_S", box, "", "_M", 0.5, "_O", 90.0, [35, -20]],
        [[15, -6], "_S", box, "", [20, -20]],
        [[15, -12], {"handles": ["8A"]}, "", [15, -12]],
        [[37, 49], box, "", [45, 50]],
    ]
    assert all(c == "BACTION" for c, _, _ in runs.calls) and doc.variables["BACTIONBARMODE"] == 1
    for bad in [lambda: block_authoring.add_action("array", [0, 0], box),
                lambda: block_authoring.add_action("scale", [0, 0], box, offset=90),
                lambda: block_authoring.add_action("move", [0, 0], box, end="middle")]:
        with pytest.raises(ValueError):
            bad()


# ---------- acad_status health (GAP-017 c) ----------


def test_crash_windows_of_any_process_are_found(monkeypatch):
    from autocad_mcp import winui as real  # no fake_app here, so these are the real helpers
    desk = _Desktop({1: (42, "AfxFrame", "AutoCAD 2027", True, []),
                     2: (42, "#32770", "AutoCAD Error Aborting", True, ["OK"]),
                     3: (77, "#32770", "Autodesk Error Report", True, ["Send"]),
                     4: (88, "Window", "", True, []),           # untitled window of the crash reporter
                     5: (99, "Notepad", "notes.txt", True, [])})  # unrelated
    monkeypatch.setattr(real, "win32gui", desk)
    monkeypatch.setattr(real, "window_pid", desk.pid)
    monkeypatch.setattr(real, "process_image", lambda pid: {42: "acad.exe", 77: "senddmp.exe",
                                                            88: "senddmp.exe", 99: "notepad.exe"}[pid])
    found = real.crash_dialogs()
    assert [d["title"] for d in found] == ["AutoCAD Error Aborting", "Autodesk Error Report", ""]
    note = real.describe_crash()
    assert '"AutoCAD Error Aborting" (acad.exe)' in note and "Do not retry" in note
    monkeypatch.setattr(real, "crash_dialogs", lambda: [])
    assert real.describe_crash() == ""


def test_status_reports_health_and_warns(fake_app, monkeypatch):
    from autocad_mcp import winui
    status = documents.acad_status()
    assert status["health"] == {"autocad_not_responding": False, "crash_dialogs": [],
                                "other_autocad_mcp_servers": [], "layouts": {"active": "Model", "count": 2}}
    monkeypatch.setattr(documents, "_other_servers", lambda: [{"pid": 4242, "command": "python -m autocad_mcp"}])
    monkeypatch.setattr(winui, "is_hung", lambda hwnd: True)

    class Broken:
        @property
        def Name(self):  # noqa: N802
            raise RuntimeError("layout interface gone")
    fake_app.doc.ActiveLayout = Broken()
    health = documents.acad_status()["health"]
    assert health["layouts"] == {"error": "RuntimeError: layout interface gone"}
    assert health["warning"] == ("Windows reports AutoCAD as not responding; the active drawing's layouts did not "
                                 "answer; 1 other autocad-mcp server(s) are running; only one AI client should "
                                 "drive AutoCAD at a time.")


def test_a_timed_out_call_names_a_crash_window(fake_app, monkeypatch):
    from autocad_mcp import app as app_module
    from autocad_mcp import winui
    monkeypatch.setattr(winui, "crash_dialogs", lambda: [{"title": "AutoCAD Error Aborting", "program": "acad.exe"}])
    assert "probably crashed" in app_module._blockers(AcadTimeout("no answer"))
    gone = pywintypes.com_error(-2147023174, "The RPC server is unavailable.", None, None)
    assert "probably crashed" in app_module._blockers(gone)
    assert app_module._blockers(ValueError("bad input")) == ""


def test_other_servers_leaves_out_this_server_and_counts_launchers_once(monkeypatch):
    import types

    from autocad_mcp.tools import documents as docs_module
    rows = [types.SimpleNamespace(ProcessId=p, ParentProcessId=pp, CommandLine=c) for p, pp, c in [
        (10, 1, "uv run -m autocad_mcp"),        # this server's launcher
        (11, 10, "python -m autocad_mcp"),       # this server
        (20, 2, "autocad-mcp.exe"),              # another server's launcher...
        (21, 20, "python -m autocad_mcp"),       # ...and its Python: one server
        (30, 3, "python -m autocad_mcp")]]       # a third server

    class Wmi:
        def ExecQuery(self, query):  # noqa: N802
            assert "Win32_Process" in query
            return rows
    monkeypatch.setattr(docs_module.win32com.client, "GetObject", lambda moniker: Wmi())
    monkeypatch.setattr(docs_module.os, "getpid", lambda: 11)
    monkeypatch.setattr(docs_module.os, "getppid", lambda: 10)
    assert [s["pid"] for s in docs_module._other_servers()] == [20, 30]

    def no_wmi(moniker):
        raise OSError("WMI unavailable")
    monkeypatch.setattr(docs_module.win32com.client, "GetObject", no_wmi)
    assert docs_module._other_servers() == []
