"""Offline tests: no AutoCAD needed. Live tests are in tests/live and run only by hand."""

from __future__ import annotations

import asyncio
import math
import threading
import time

import pytest
import pywintypes
from conftest import FakeDoc, FakeEntity
from mcp.server.mcpserver.exceptions import ToolError

from autocad_mcp import com
from autocad_mcp import session as session_module
from autocad_mcp.app import _render, _where
from autocad_mcp.com import AcadError, AcadTimeout, ComWorker, deg, rad, xyz
from autocad_mcp.server import mcp
from autocad_mcp.session import Session, doc_key, product_name, session
from autocad_mcp.tools import annotate, documents, draw, edit, entities, layers, query, settings, sheets

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

