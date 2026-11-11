"""Fakes that stand in for AutoCAD so the safety logic and tools can be tested without it."""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autocad_mcp import session as session_module  # noqa: E402
from autocad_mcp.com import enums  # noqa: E402
from autocad_mcp.session import session  # noqa: E402


def _xyz(variant) -> tuple:
    return tuple(getattr(variant, "value", variant))


def _com_error(text: str):
    import pywintypes
    return pywintypes.com_error(-2147352567, "Exception occurred.", (0, "AutoCAD.Application", text, None, 0, 0), None)


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


class FakeLine(FakeEntity):
    def GetBoundingBox(self):  # noqa: N802
        (x1, y1, _), (x2, y2, _) = self.StartPoint, self.EndPoint
        return (min(x1, x2), min(y1, y2), 0.0), (max(x1, x2), max(y1, y2), 0.0)


class FakeDynProp:
    def __init__(self, name: str, value, allowed=(), show: bool = True) -> None:
        self.PropertyName, self.Value, self.AllowedValues, self.Show, self.ReadOnly = name, value, allowed, show, False


class FakeAttribute:
    def __init__(self, tag: str, text: str, invisible: bool) -> None:
        self.TagString, self.TextString, self.Invisible = tag, text, invisible

    def Update(self) -> None:  # noqa: N802
        pass


class FakeBlockRef(FakeEntity):
    """A placed screw block: Size (lookup) sets the width, Length the tip; Visibility1 is a hidden helper."""

    WIDTHS = {"#8-18": 0.348, "#10-16": 0.414, "#12-14": 0.432}

    def __init__(self, doc: FakeDoc, block: str, insertion) -> None:
        super().__init__(doc, "AcDbBlockReference", Name="*U12", EffectiveName=block, IsDynamicBlock=True,
                         InsertionPoint=tuple(insertion), HasAttributes=True, Rotation=0.0,
                         XScaleFactor=1.0, YScaleFactor=1.0, ZScaleFactor=1.0)
        self.props = [FakeDynProp("Size", "#12-14", tuple(self.WIDTHS)),
                      FakeDynProp("Length", 1.0, (0.5, 0.75, 1.0, 1.25, 2.0)),
                      FakeDynProp("Visibility1", "#12-14", tuple(self.WIDTHS), show=False),
                      FakeDynProp("Origin", (0.0, 0.0), show=False)]
        self.atts = [FakeAttribute("CALLOUT", "#12-14 x 1\" HWH TEK", True), FakeAttribute("SPEC", "", True)]

    def GetDynamicBlockProperties(self):  # noqa: N802
        return list(self.props)

    def GetAttributes(self):  # noqa: N802
        return list(self.atts)

    def value(self, name: str):
        return next(p.Value for p in self.props if p.PropertyName == name)

    def Explode(self):  # noqa: N802
        x, y, _ = self.InsertionPoint
        half = self.WIDTHS[self.value("Size")] / 2
        space = self._space
        parts = [FakeLine(self._doc, "AcDbLine", StartPoint=(x - half, y, 0.0), EndPoint=(x + half, y, 0.0)),
                 FakeLine(self._doc, "AcDbLine", StartPoint=(x, y, 0.0), EndPoint=(x, y - self.value("Length"), 0.0)),
                 FakeEntity(self._doc, "AcDbAttributeDefinition")]
        for p in parts:
            space._add(p)
        return parts


class FakeSpace:
    def __init__(self, doc: FakeDoc) -> None:
        self.doc, self.items = doc, []

    def InsertBlock(self, insertion, block, xs, ys, zs, rotation):  # noqa: N802
        return self._add(FakeBlockRef(self.doc, block, _xyz(insertion)))

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

    def AddAttribute(self, height, mode, prompt, insertion, tag, value):  # noqa: N802
        return self._add(FakeEntity(self.doc, "AcDbAttributeDefinition", Height=height, Mode=mode,
                                    PromptString=prompt, InsertionPoint=_xyz(insertion), TagString=tag,
                                    TextString=value))  # the tag keeps its case, as over COM (2026-11-10)

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
    PAPERS = {"ANSI_A_(11.00_x_8.50_Inches)": "ANSI A (11.00 x 8.50 Inches)",
              "ANSI_B_(17.00_x_11.00_Inches)": "ANSI B (17.00 x 11.00 Inches)",
              "ANSI_full_bleed_B_(17.00_x_11.00_Inches)": "ANSI full bleed B (17.00 x 11.00 Inches)",
              "ANSI_B_(11.00_x_17.00_Inches)": "ANSI B (11.00 x 17.00 Inches)"}

    def __init__(self, name: str, tab_order: int, block: FakeSpace, model: bool = False) -> None:
        self.Name, self.TabOrder, self.Block, self.ModelType = name, tab_order, block, model
        self.ConfigName, self._media, self.StyleSheet = "None", "Letter_(8.50_x_11.00_Inches)", ""
        self.PlotType, self.PlotRotation, self.UseStandardScale, self.StandardScale = 0, 1, False, 0
        self.refreshed = 0

    @property
    def CanonicalMediaName(self) -> str:  # noqa: N802
        return self._media

    @CanonicalMediaName.setter
    def CanonicalMediaName(self, value: str) -> None:  # noqa: N802
        if not value:  # AutoCAD refuses an empty paper name (live 2026-11-11)
            raise _com_error("Invalid input")
        self._media = value

    def RefreshPlotDeviceInfo(self) -> None:  # noqa: N802
        self.refreshed += 1

    def GetPlotDeviceNames(self):  # noqa: N802
        return ("None", "DWG To PDF.pc3")

    def GetCanonicalMediaNames(self):  # noqa: N802
        return tuple(self.PAPERS)

    def GetLocaleMediaName(self, name: str) -> str:  # noqa: N802
        return self.PAPERS.get(name, name)

    def GetPlotStyleTableNames(self):  # noqa: N802
        return ("acad.ctb", "monochrome.ctb", "monochrome.stb")


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


class FakeNamed:
    """A named collection (DimStyles, TextStyles) or dictionary of styles."""

    class Style:
        def __init__(self, name: str, collection: FakeNamed | None = None) -> None:
            self.Name, self.collection, self.copied = name, collection, None
            self.FontFile, self.Height, self.Width, self.ObliqueAngle = "txt.shx", 0.0, 1.0, 0.0  # text style
            self.ScaleFactor, self.TextHeight, self.ArrowSize, self._text_style = 1.0, 0.18, 0.18, "Standard"
            self.LandingGap, self.DoglegLength = 0.09, 0.36  # multileader style

        def CopyFrom(self, source) -> None:  # noqa: N802 - a dimension style takes the drawing's settings
            self.copied = dict(source.variables)

        def Delete(self) -> None:  # noqa: N802
            self.collection.items.remove(self)

        @property
        def TextStyle(self) -> str:  # noqa: N802
            if self._text_style is None:  # a multileader style made over COM has none (live 2026-11-11)
                raise _com_error("Null object ID")
            return self._text_style

        @TextStyle.setter
        def TextStyle(self, value: str) -> None:  # noqa: N802
            self._text_style = value

    def __init__(self, items: list) -> None:
        self.items = items

    def Add(self, name: str):  # noqa: N802
        style = FakeNamed.Style(name, self)
        self.items.append(style)
        return style

    def AddObject(self, name: str, class_name: str):  # noqa: N802
        assert class_name == "AcDbMLeaderStyle"
        style = self.Add(name)
        style._text_style = None
        return style

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self.items)

    def Item(self, i: int):  # noqa: N802
        return self.items[i]

    def GetName(self, obj) -> str:  # noqa: N802
        return obj.Name


class FakeDoc:
    _next_window = 0x5000

    def __init__(self, name: str = "Drawing1.dwg", full_name: str = "") -> None:
        self.Name, self.FullName = name, full_name
        self.Saved, self.ReadOnly = True, False
        self.variables = {"CMDACTIVE": 0, "INSUNITS": 4, "MEASUREMENT": 1}
        self.undo_log: list[str] = []
        self.fail_next_add = False
        FakeDoc._next_window += 1
        self.HWND = FakeDoc._next_window  # a new document window each time a drawing is opened
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
        self.DimStyles = FakeNamed([self.ActiveDimStyle, FakeNamed.Style("ARCH-DIM")])
        self.TextStyles = FakeNamed([FakeNamed.Style("Standard"), FakeNamed.Style("NOTES-TEXT")])
        self.ActiveTextStyle = self.TextStyles.Item(0)
        self.variables["CMLEADERSTYLE"] = "Standard"

        mleader_styles = FakeNamed([FakeNamed.Style("Standard"), FakeNamed.Style("NOTES")])

        class _Dictionaries:
            def Item(self, key: str):  # noqa: N802
                assert key == "ACAD_MLEADERSTYLE"
                return mleader_styles
        self.Dictionaries = _Dictionaries()

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

    def Open(self, path: str, read_only: bool = False):  # noqa: N802
        doc = FakeDoc(os.path.basename(path), path)
        doc.ReadOnly = read_only
        self.docs.append(doc)
        return doc


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
def fake_app(monkeypatch, tmp_path):
    app = FakeApp()
    monkeypatch.setattr(session, "_app", app)
    monkeypatch.setattr(session, "owned", set())
    monkeypatch.setattr(session, "owned_windows", {})
    monkeypatch.setattr(session, "identity", None)  # no ownership record unless a test sets one
    monkeypatch.setattr(session_module, "OWNED_RECORD", tmp_path / "owned.json")
    monkeypatch.setattr(session, "unlocked", set())
    monkeypatch.setattr(session, "allow_all_edits", False)
    monkeypatch.setattr(enums, "_values", {
        "acRed": 1, "acVpCustomScale": 1, "acLayout": 5, "ac0degrees": 0, "ac1_1": 16,
        "acAttributeModeInvisible": 1, "acAttributeModeConstant": 2, "acAttributeModePreset": 8,
        "acAttributeModeLockPosition": 16})
    monkeypatch.setattr(session_module, "SETTLE_PAUSE", 0)
    monkeypatch.setattr(session, "hwnd", None)
    return app
