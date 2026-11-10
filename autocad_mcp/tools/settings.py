"""Drawing settings: a short list of system variables that are saved in the drawing."""

from __future__ import annotations

import pywintypes

from ..app import acad_tool
from ..com import AcadError, deg, rad
from ..session import session
from .entities import model_space

# Name -> (type, minimum, maximum, meaning). Only variables stored in the drawing, so
# changing them never touches the user's AutoCAD profile. Text variables list their
# allowed values in SEPARATORS instead of a range.
VARIABLES: dict[str, tuple[type, float, float, str]] = {
    "DIMSCALE": (float, 0, 10_000, "overall dimension scale (e.g. 48 for 1/4\"=1'-0\", 24 for 1/2\"=1'-0\")"),
    "DIMTXT": (float, 0.001, 1_000, "dimension text height, before DIMSCALE"),
    "DIMASZ": (float, 0, 1_000, "dimension arrow size, before DIMSCALE"),
    "DIMLUNIT": (int, 1, 6, "dimension units: 1 scientific, 2 decimal, 3 engineering, 4 architectural, "
                            "5 fractional, 6 Windows desktop"),
    "DIMDEC": (int, 0, 8, "dimension precision"),
    "DIMDSEP": (str, 0, 0, "decimal separator of decimal dimensions: \".\" or \",\""),
    "DIMZIN": (int, 0, 15, "zero suppression in architectural units: 3 shows 14'-0\" and 6\", "
                         "1 shows 14'-0\" and 0'-6\", 0 shows 14' and 6\""),
    "DIMTAD": (int, 0, 4, "dimension text position: 0 centred in the dimension line, 1 above it, 2 outside, "
                          "3 JIS, 4 below"),
    "DIMTIH": (int, 0, 1, "text between the extension lines: 1 horizontal, 0 along the dimension line"),
    "DIMTOH": (int, 0, 1, "text outside the extension lines: 1 horizontal, 0 along the dimension line"),
    "DIMFRAC": (int, 0, 2, "fraction format: 0 stacked, 1 diagonal, 2 not stacked (1 1/2)"),
    "DIMEXO": (float, 0, 1_000, "gap between the object and its extension lines, before DIMSCALE"),
    "DIMEXE": (float, 0, 1_000, "how far extension lines pass the dimension line, before DIMSCALE"),
    "DIMGAP": (float, -1_000, 1_000, "gap around dimension text, before DIMSCALE (negative boxes the text)"),
    "LTSCALE": (float, 0.001, 10_000, "global linetype scale"),
    "LUNITS": (int, 1, 5, "length units: 1 scientific, 2 decimal, 3 engineering, 4 architectural, 5 fractional"),
    "LUPREC": (int, 0, 8, "length display precision"),
    "INSUNITS": (int, 0, 21, "drawing units (1 inches, 4 millimeters, ...)"),
    "TEXTSIZE": (float, 0.001, 10_000, "default text height"),
}
SEPARATORS = (".", ",")
# What add_dimension_style calls each arrowhead -> the value DIMBLK takes ("." is the default closed filled arrow).
ARROWHEADS = {
    "closed_filled": ".", "closed_blank": "_CLOSEDBLANK", "closed": "_CLOSED", "open": "_OPEN",
    "open30": "_OPEN30", "right_angle": "_OPEN90", "dot": "_DOT", "dot_small": "_DOTSMALL",
    "tick": "_ARCHTICK", "oblique": "_OBLIQUE", "none": "_NONE",
}
FONT_FILES = (".shx", ".ttf", ".ttc", ".otf")
NAME_BANNED = set('<>/\\":;?*|,=`')
MLEADER_SIZES = ("TextHeight", "ArrowSize", "LandingGap", "DoglegLength")


def style_name(value: str, kind: str) -> str:
    """A name AutoCAD accepts for a style, or an error."""
    text = value.strip()
    if not text or len(text) > 255 or NAME_BANNED & set(text):
        raise AcadError(f"'{value}' is not a usable {kind} name (no < > / \\ \" : ; ? * | , = `).")
    return text


def find_named(collection, wanted: str):
    """The item with this name (ignoring case), or None."""
    for i in range(collection.Count):
        item = collection.Item(i)
        if str(item.Name).lower() == wanted.strip().lower():
            return item
    return None


def rebuild_dimensions(doc, style: str) -> int:
    """Existing dimensions keep the picture they were built with until each one is updated;
    REGEN alone does not rebuild them (verified 2026-10-29). Returns how many were rebuilt."""
    rebuilt = 0
    for ent in model_space(doc):
        if "Dimension" in str(ent.ObjectName) and str(ent.StyleName) == style:
            ent.Update()
            rebuilt += 1
    doc.Regen(1)  # acAllViewports
    return rebuilt


def checked(variables: dict[str, float | str]) -> dict[str, float | str]:
    """The variables by upper-case name, with values of the right type, or an error that says
    what is wrong. Nothing in AutoCAD is touched."""
    if not variables:
        raise AcadError("Give at least one variable.")
    values = {}
    for var, value in variables.items():
        key = var.strip().upper()
        if key not in VARIABLES:
            raise AcadError(f"{var} is not one of {', '.join(VARIABLES)}.")
        kind, low, high, meaning = VARIABLES[key]
        if kind is str:
            if value not in SEPARATORS:
                raise AcadError(f"{key} must be one of {' or '.join(repr(s) for s in SEPARATORS)} ({meaning}).")
            values[key] = value
            continue
        number = kind(value)
        if kind is int and number != value:
            raise AcadError(f"{key} must be a whole number ({meaning}).")
        if not low <= number <= high:
            raise AcadError(f"{key} must be between {low} and {high} ({meaning}).")
        values[key] = number
    return values


@acad_tool(read_only=True)
def get_drawing_variables(name: str = "") -> dict:
    """Read the drawing settings that set_drawing_variables can change (dimension scale,
    units, linetype scale...).

    Args:
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    return {var: doc.GetVariable(var) for var in VARIABLES}


@acad_tool()
def set_drawing_variables(variables: dict[str, float | str], name: str = "") -> dict:
    """Change drawing settings saved in the drawing, e.g. {"DIMSCALE": 24, "DIMLUNIT": 4,
    "LUNITS": 4, "LTSCALE": 12} for a 1/2"=1'-0" architectural drawing. DIM* values are
    also copied into the active dimension style, and model space dimensions on that style
    are rebuilt with them. One undo step; restored if any value fails.

    Allowed: DIMSCALE, DIMTXT, DIMASZ, DIMLUNIT, DIMDEC, DIMDSEP, DIMZIN, DIMTAD, DIMTIH, DIMTOH,
    DIMFRAC, DIMEXO, DIMEXE, DIMGAP, LTSCALE, LUNITS, LUPREC, INSUNITS, TEXTSIZE. DIMDSEP is "."
    or ","; a style made for metric drawings often has ",", so set "." together with DIMLUNIT 2
    for 1.00 rather than 1,00. For text above the dimension line and along it: DIMTAD 1,
    DIMTIH 0, DIMTOH 0.

    Args:
        variables: name -> new value.
        name: which open drawing (default: active).
    """
    values = checked(variables)
    doc = session.document(name)
    dim_keys = [k for k in values if k.startswith("DIM")]
    with session.edit(doc) as change:
        if dim_keys:
            # Dimensions made through COM follow the active style and ignore DIM* overrides
            # (verified 2026-10-29), so the style itself is updated. Registered first so that,
            # on rollback, it runs last: after the old values are back.
            style = doc.ActiveDimStyle
            change.on_rollback(lambda: style.CopyFrom(doc))
        for key, value in values.items():
            old = doc.GetVariable(key)
            change.on_rollback(lambda k=key, o=old: doc.SetVariable(k, o))
            doc.SetVariable(key, value)
        result = {key: doc.GetVariable(key) for key in values}
        if dim_keys:
            style.CopyFrom(doc)
            result["dimension_style_updated"] = str(style.Name)
            result["dimensions_rebuilt"] = rebuild_dimensions(doc, str(style.Name))
        return result


def _style(collection, wanted: str, kind: str):
    names = [str(collection.Item(i).Name) for i in range(collection.Count)]
    for i, found in enumerate(names):
        if found.lower() == wanted.strip().lower():
            return collection.Item(i)
    raise AcadError(f"No {kind} named '{wanted}'. The drawing has: {', '.join(names)}.")


@acad_tool()
def set_current_styles(dimension_style: str = "", multileader_style: str = "", text_style: str = "",
                       name: str = "") -> dict:
    """Make styles that are already in the drawing (usually from its template) current, so new
    dimensions, leaders and text use them. Nothing already drawn changes. One undo step.

    Args:
        dimension_style: name of a dimension style to make current.
        multileader_style: name of a multileader style to make current (used by add_leader).
        text_style: name of a text style to make current.
        name: which open drawing (default: active).
    """
    if not (dimension_style or multileader_style or text_style):
        raise AcadError("Give at least one style name.")
    doc = session.document(name)
    with session.edit(doc) as change:
        out = {}
        if dimension_style:
            style, previous = _style(doc.DimStyles, dimension_style, "dimension style"), doc.ActiveDimStyle
            doc.ActiveDimStyle = style
            change.on_rollback(lambda: setattr(doc, "ActiveDimStyle", previous))
            out["dimension_style"] = str(style.Name)
        if text_style:
            style, previous_text = _style(doc.TextStyles, text_style, "text style"), doc.ActiveTextStyle
            doc.ActiveTextStyle = style
            change.on_rollback(lambda: setattr(doc, "ActiveTextStyle", previous_text))
            out["text_style"] = str(style.Name)
        if multileader_style:
            # Multileader styles have no ActiveX collection; they live in this named dictionary.
            styles = doc.Dictionaries.Item("ACAD_MLEADERSTYLE")
            names = [str(styles.GetName(styles.Item(i))) for i in range(styles.Count)]
            match = next((n for n in names if n.lower() == multileader_style.strip().lower()), None)
            if match is None:
                raise AcadError(f"No multileader style named '{multileader_style}'. The drawing has: "
                                f"{', '.join(names)}.")
            previous_ml = doc.GetVariable("CMLEADERSTYLE")
            doc.SetVariable("CMLEADERSTYLE", match)
            change.on_rollback(lambda: doc.SetVariable("CMLEADERSTYLE", previous_ml))
            out["multileader_style"] = match
        return out


@acad_tool()
def add_text_style(style: str, font: str = "romans.shx", height: float = 0, width_factor: float = 1,
                   oblique_angle: float = 0, make_current: bool = False, name: str = "") -> dict:
    """Create a text style, or change the font and proportions of an existing one (text already
    drawn in it follows). One undo step.

    Args:
        style: text style name, e.g. "NOTES".
        font: a font file: an AutoCAD .shx (romans.shx, simplex.shx, txt.shx) or a TrueType
            file from the Windows Fonts folder (arial.ttf), by file name or full path.
        height: fixed text height in drawing units; 0, the usual choice, lets each text and
            dimension set its own height.
        width_factor: character width, 1 is normal (0.01 to 100).
        oblique_angle: slant in degrees, -85 to 85.
        make_current: also make it the current text style.
        name: which open drawing (default: active).
    """
    label = style_name(style, "text style")
    if not font.lower().endswith(FONT_FILES):
        raise AcadError(f"font must be a font file name ending in {', '.join(FONT_FILES)}, "
                        "e.g. romans.shx or arial.ttf.")
    if height < 0:
        raise AcadError("height cannot be negative (0 means not fixed).")
    if not 0.01 <= width_factor <= 100:
        raise AcadError("width_factor must be between 0.01 and 100.")
    if not -85 <= oblique_angle <= 85:
        raise AcadError("oblique_angle must be between -85 and 85 degrees.")
    doc = session.document(name)
    with session.edit(doc) as change:
        target = find_named(doc.TextStyles, label)
        created = target is None
        if created:
            target = change.add(doc.TextStyles.Add(label))
        else:
            old = (str(target.FontFile), float(target.Height), float(target.Width), float(target.ObliqueAngle))

            def restore(t=target, o=old) -> None:
                t.FontFile, t.Height, t.Width, t.ObliqueAngle = o
            change.on_rollback(restore)
        try:
            target.FontFile = font
        except pywintypes.com_error:
            raise AcadError(f"AutoCAD could not use the font file '{font}'. Check the name.") from None
        target.Height = float(height)
        target.Width = float(width_factor)
        target.ObliqueAngle = rad(oblique_angle)
        if make_current:
            previous = doc.ActiveTextStyle
            doc.ActiveTextStyle = target
            change.on_rollback(lambda: setattr(doc, "ActiveTextStyle", previous))
        if not created:
            doc.Regen(1)  # text already drawn shows the new font only after a regen
        return {"name": str(target.Name), "font": str(target.FontFile), "height": float(target.Height),
                "width_factor": float(target.Width), "oblique_angle": round(deg(float(target.ObliqueAngle)), 6),
                "created": created, "current": str(doc.ActiveTextStyle.Name).lower() == label.lower()}


@acad_tool()
def add_dimension_style(style: str, variables: dict[str, float | str] | None = None, text_style: str = "",
                        arrowhead: str = "", name: str = "") -> dict:
    """Create a dimension style from the current dimension settings plus the changes given
    here, or apply the changes to an existing style. The style becomes the current one, so new
    dimensions use it. One undo step.

    A new style starts as a copy of the current style. When an existing style is changed, its
    model space dimensions are rebuilt with the new settings.

    Args:
        style: dimension style name, e.g. "STEEL-3IN" (one style per plot scale is common,
            each with its own DIMSCALE).
        variables: DIM* settings by name, the ones set_drawing_variables takes, e.g.
            {"DIMSCALE": 4, "DIMTXT": 0.09375, "DIMASZ": 0.09375, "DIMLUNIT": 4, "DIMTAD": 1,
            "DIMTIH": 0, "DIMTOH": 0, "DIMFRAC": 2}.
        text_style: an existing text style for the dimension text (see add_text_style).
        arrowhead: closed_filled, closed_blank, closed, open, open30, right_angle, dot,
            dot_small, tick (architectural tick), oblique or none.
        name: which open drawing (default: active).
    """
    label = style_name(style, "dimension style")
    values = checked(variables) if variables else {}
    other = [key for key in values if not key.startswith("DIM")]
    if other:
        raise AcadError(f"{', '.join(other)}: not a dimension setting; use set_drawing_variables for it.")
    arrow = arrowhead.strip().lower()
    if arrow and arrow not in ARROWHEADS:
        raise AcadError(f"arrowhead must be one of {', '.join(ARROWHEADS)}.")
    doc = session.document(name)
    with session.edit(doc) as change:
        if text_style:
            values["DIMTXSTY"] = str(_style(doc.TextStyles, text_style, "text style").Name)
        if arrow:
            values["DIMBLK"] = ARROWHEADS[arrow]
        previous = doc.ActiveDimStyle
        target = find_named(doc.DimStyles, label)
        created = target is None
        if created:
            target = change.add(doc.DimStyles.Add(label))
        elif str(previous.Name).lower() != label.lower():
            # The drawing's DIM* variables describe the current style: switch to it first, then change them.
            doc.ActiveDimStyle = target
            change.on_rollback(lambda: setattr(doc, "ActiveDimStyle", previous))
        for var, value in values.items():
            old = doc.GetVariable(var)
            # DIMBLK reads back "" for the default arrow but only takes "." to set it.
            back = "." if var == "DIMBLK" and old == "" else old
            change.on_rollback(lambda v=var, o=back: doc.SetVariable(v, o))
            doc.SetVariable(var, value)
        target.CopyFrom(doc)  # the current style's settings plus the changes above
        if created:
            doc.ActiveDimStyle = target
            change.on_rollback(lambda: setattr(doc, "ActiveDimStyle", previous))
        result = {"name": str(target.Name), "created": created, "current": True,
                  "settings": {var: doc.GetVariable(var) for var in values}}
        if not created:
            result["dimensions_rebuilt"] = rebuild_dimensions(doc, str(target.Name))
        return result


@acad_tool()
def add_multileader_style(style: str, scale: float = 1, text_height: float = 0, arrow_size: float = 0,
                          text_style: str = "", make_current: bool = True, name: str = "") -> dict:
    """Create a multileader style for add_leader, or change an existing one. Give it the plot
    scale factor so callouts come out the same size on paper as dimensions: 4 for 3" = 1'-0",
    48 for 1/4" = 1'-0", like DIMSCALE. One undo step.

    A new style starts with the text, arrow and landing sizes of the current multileader style.

    Args:
        style: multileader style name, e.g. "NOTES-3IN".
        scale: overall scale factor applied to the text, arrow and landing sizes.
        text_height: text height on paper, before scale (0 keeps the style's height).
        arrow_size: arrowhead size on paper, before scale (0 keeps the style's size).
        text_style: an existing text style for the callout text (see add_text_style).
        make_current: make it the current multileader style, so add_leader uses it (default True).
        name: which open drawing (default: active).
    """
    label = style_name(style, "multileader style")
    if scale <= 0:
        raise AcadError("scale must be positive.")
    if text_height < 0 or arrow_size < 0:
        raise AcadError("text_height and arrow_size cannot be negative (0 keeps the style's value).")
    doc = session.document(name)
    with session.edit(doc) as change:
        # Multileader styles have no ActiveX collection; they live in this named dictionary.
        styles = doc.Dictionaries.Item("ACAD_MLEADERSTYLE")
        by_name = {}
        for i in range(styles.Count):
            item = styles.Item(i)
            by_name[str(styles.GetName(item)).lower()] = (str(styles.GetName(item)), item)
        created = label.lower() not in by_name
        if created:
            target = change.add(styles.AddObject(label, "AcDbMLeaderStyle"))
            base = by_name.get(str(doc.GetVariable("CMLEADERSTYLE")).lower())
            for prop in MLEADER_SIZES if base else ():
                setattr(target, prop, getattr(base[1], prop))
        else:
            label, target = by_name[label.lower()]
            old = [(prop, getattr(target, prop)) for prop in ("ScaleFactor", "TextHeight", "ArrowSize", "TextStyle")]

            def restore(t=target, o=old) -> None:
                for prop, value in o:
                    setattr(t, prop, value)
            change.on_rollback(restore)
        target.ScaleFactor = float(scale)
        if text_height:
            target.TextHeight = float(text_height)
        if arrow_size:
            target.ArrowSize = float(arrow_size)
        if text_style:
            target.TextStyle = str(_style(doc.TextStyles, text_style, "text style").Name)
        if make_current:
            previous = doc.GetVariable("CMLEADERSTYLE")
            doc.SetVariable("CMLEADERSTYLE", label)
            change.on_rollback(lambda: doc.SetVariable("CMLEADERSTYLE", previous))
        return {"name": label, "created": created, "scale": float(target.ScaleFactor),
                "text_height": float(target.TextHeight), "arrow_size": float(target.ArrowSize),
                "text_style": str(target.TextStyle),
                "current": str(doc.GetVariable("CMLEADERSTYLE")).lower() == label.lower()}
