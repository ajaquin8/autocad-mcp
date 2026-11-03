"""Fakes that stand in for AutoCAD so the safety logic and tools can be tested without it."""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autocad_mcp.com import enums  # noqa: E402
from autocad_mcp.session import session  # noqa: E402


def _xyz(variant) -> tuple:
    return tuple(getattr(variant, "value", variant))


class FakeEntity:
    _next_handle = 0x100

    def __init__(self, doc: FakeDoc, object_name: str, **props) -> None:
        FakeEntity._next_handle += 1
        self.Handle = f"{FakeEntity._next_handle:X}"
        self.ObjectName = object_name
        self.Layer = "0"
        self.color = 256
        self.Linetype = "ByLayer"
        self.deleted = False
        self._doc = doc
        self.__dict__.update(props)

    def Update(self) -> None:  # noqa: N802 - mirrors the COM API
        pass

    def Delete(self) -> None:  # noqa: N802
        self.deleted = True
        (getattr(self, "_space", None) or self._doc.space).items.remove(self)

    def Move(self, origin, target) -> None:  # noqa: N802
        self.moved = (_xyz(origin), _xyz(target))

    def GetBoundingBox(self):  # noqa: N802
        return (0.0, 0.0, 0.0), (1.0, 1.0, 0.0)


class FakeSpace:
    def __init__(self, doc: FakeDoc) -> None:
        self.doc, self.items = doc, []

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self.items)

    def Item(self, i: int):  # noqa: N802
        return self.items[i]

    def _add(self, ent: FakeEntity) -> FakeEntity:
        if self.doc.fail_next_add:
            raise RuntimeError("AutoCAD refused")
        ent._space = self
        self.items.append(ent)
        return ent

    def AddLine(self, start, end):  # noqa: N802
        s, e = _xyz(start), _xyz(end)
        return self._add(FakeEntity(self.doc, "AcDbLine", StartPoint=s, EndPoint=e,
                                    Length=math.dist(s, e), Angle=math.atan2(e[1] - s[1], e[0] - s[0])))

    def AddCircle(self, center, radius):  # noqa: N802
        return self._add(FakeEntity(self.doc, "AcDbCircle", Center=_xyz(center), Radius=radius))

    def AddMLeader(self, points, index):  # noqa: N802
        flat = list(_xyz(points))
        triples = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
        return self._add(FakeEntity(self.doc, "AcDbMLeader", points=triples, TextString="")), index

    def AddDimDiametric(self, chord, far_chord, leader_length):  # noqa: N802
        return self._add(FakeEntity(self.doc, "AcDbDiametricDimension", chord=_xyz(chord), far=_xyz(far_chord),
                                    leader=leader_length, TextOverride="",
                                    Measurement=math.dist(_xyz(chord), _xyz(far_chord))))

    def AddDimRadial(self, center, chord, leader_length):  # noqa: N802
        return self._add(FakeEntity(self.doc, "AcDbRadialDimension", center=_xyz(center), chord=_xyz(chord),
                                    leader=leader_length, TextOverride="",
                                    Measurement=math.dist(_xyz(center), _xyz(chord))))

    def AddPViewport(self, center, width, height):  # noqa: N802
        if self.doc.ActiveLayout.ModelType:
            raise RuntimeError("paper space is not active")
        return self._add(FakeViewport(self.doc, "AcDbViewport", Center=_xyz(center), Width=width, Height=height,
                                      StandardScale=0, CustomScale=1.0, DisplayLocked=False, displayed=False))


class FakeViewport(FakeEntity):
    def Display(self, on: bool) -> None:  # noqa: N802
        self.displayed = on


class FakeLayout:
    def __init__(self, name: str, tab_order: int, block: FakeSpace, model: bool = False) -> None:
        self.Name, self.TabOrder, self.Block, self.ModelType = name, tab_order, block, model


class FakeLayouts:
    def __init__(self, layouts: list[FakeLayout]) -> None:
        self.items = layouts

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self.items)

    def Item(self, i: int) -> FakeLayout:  # noqa: N802
        return self.items[i]


class FakeLayer:
    def __init__(self, name: str) -> None:
        self.Name, self.color, self.Linetype, self.Lineweight = name, 7, "Continuous", -3
        self.Description, self.LayerOn, self.Freeze, self.Lock, self.Plottable = "", True, False, False, True
        self.collection: FakeLayers | None = None

    def Delete(self) -> None:  # noqa: N802
        del self.collection.items[self.Name]


class FakeLayers:
    def __init__(self) -> None:
        self.items = {"0": FakeLayer("0")}

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self.items)

    def Item(self, key):  # noqa: N802
        import pywintypes
        if isinstance(key, int):
            return list(self.items.values())[key]
        for name, layer in self.items.items():
            if name.lower() == str(key).lower():
                return layer
        raise pywintypes.com_error(-2145386476, "Key not found", None, None)

    def Add(self, name: str):  # noqa: N802
        layer = self.items[name] = FakeLayer(name)
        layer.collection = self
        return layer


class FakeLinetypes:
    def __init__(self) -> None:
        self.names = {"continuous", "bylayer", "byblock"}
        self.loaded: list[tuple[str, str]] = []

    def Item(self, name: str):  # noqa: N802
        import pywintypes
        if name.lower() not in self.names:
            raise pywintypes.com_error(-2145386476, "Key not found", None, None)
        return name

    def Load(self, name: str, lin_file: str) -> None:  # noqa: N802
        self.loaded.append((name, lin_file))
        self.names.add(name.lower())


class FakeDoc:
    def __init__(self, name: str = "Drawing1.dwg", full_name: str = "") -> None:
        self.Name, self.FullName = name, full_name
        self.Saved, self.ReadOnly = True, False
        self.variables = {"CMDACTIVE": 0, "INSUNITS": 4, "MEASUREMENT": 1}
        self.undo_log: list[str] = []
        self.fail_next_add = False
        self.space = FakeSpace(self)
        self.Layers = FakeLayers()
        self.Linetypes = FakeLinetypes()
        self.ActiveLayer = self.Layers.Item("0")
        self.paper = FakeSpace(self)
        self.Layouts = FakeLayouts([FakeLayout("Sheet1", 1, self.paper), FakeLayout("Model", 0, self.space, True)])
        self.ActiveLayout = self.Layouts.Item(1)
        self.MSpace, self.ActivePViewport = False, None
        doc = self

        class _DimStyle:
            Name = "Standard"

            def CopyFrom(self, source) -> None:  # noqa: N802
                doc.undo_log.append(f"style DIMSCALE={source.variables.get('DIMSCALE')}")
        self.ActiveDimStyle = _DimStyle()

    def Regen(self, which: int) -> None:  # noqa: N802
        self.undo_log.append("regen")

    @property
    def ModelSpace(self):  # noqa: N802
        return self.space

    @property
    def PaperSpace(self):  # noqa: N802
        return self.ActiveLayout.Block

    def GetVariable(self, name: str):  # noqa: N802
        return self.variables.get(name, 1.0)

    def SetVariable(self, name: str, value) -> None:  # noqa: N802
        if value == -999:
            raise RuntimeError("AutoCAD refused the value")
        self.variables[name] = value

    def StartUndoMark(self) -> None:  # noqa: N802
        self.undo_log.append("start")

    def EndUndoMark(self) -> None:  # noqa: N802
        self.undo_log.append("end")

    def HandleToObject(self, handle: str):  # noqa: N802
        import pywintypes
        for ent in self.space.items + self.paper.items:
            if ent.Handle == handle:
                return ent
        raise pywintypes.com_error(-2145386484, "Unknown handle", None, None)


class FakeDocuments:
    def __init__(self, docs: list[FakeDoc]) -> None:
        self.docs = docs

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self.docs)

    def Item(self, i: int) -> FakeDoc:  # noqa: N802
        return self.docs[i]

    def Add(self, template: str = ""):  # noqa: N802
        """Like AutoCAD 2027: the returned proxy cannot resolve every member (ReadOnly failed live)."""
        doc = FakeDoc(f"Drawing{len(self.docs) + 1}.dwg")
        self.docs.append(doc)

        class _Returned:
            Name = doc.Name
        return _Returned()


class FakeApp:
    """Just enough of AutoCAD.Application for Session and the tools."""

    def __init__(self) -> None:
        self.Name, self.Version = "AutoCAD", "26.0s (LMS Tech)"
        self.doc = FakeDoc()
        self.Documents = FakeDocuments([self.doc])
        self.quiescent = True

    @property
    def ActiveDocument(self):  # noqa: N802
        return self.Documents.docs[0]

    def ZoomWindow(self, lower_left, upper_right) -> None:  # noqa: N802
        self.zoomed = (_xyz(lower_left), _xyz(upper_right), self.ActiveDocument.MSpace)

    def GetAcadState(self):  # noqa: N802
        class _State:
            IsQuiescent = self.quiescent
        return _State()


@pytest.fixture()
def fake_app(monkeypatch):
    app = FakeApp()
    monkeypatch.setattr(session, "_app", app)
    monkeypatch.setattr(session, "owned", set())
    monkeypatch.setattr(session, "unlocked", set())
    monkeypatch.setattr(session, "allow_all_edits", False)
    monkeypatch.setattr(enums, "_values", {"acRed": 1, "acVpCustomScale": 1})
    return app
