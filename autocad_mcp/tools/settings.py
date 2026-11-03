"""Drawing settings: a short list of system variables that are saved in the drawing."""

from __future__ import annotations

from ..app import acad_tool
from ..com import AcadError
from ..session import session
from .entities import model_space

# Name -> (type, minimum, maximum, meaning). Only variables stored in the drawing, so
# changing them never touches the user's AutoCAD profile.
VARIABLES: dict[str, tuple[type, float, float, str]] = {
    "DIMSCALE": (float, 0, 10_000, "overall dimension scale (e.g. 48 for 1/4\"=1'-0\", 24 for 1/2\"=1'-0\")"),
    "DIMTXT": (float, 0.001, 1_000, "dimension text height, before DIMSCALE"),
    "DIMASZ": (float, 0, 1_000, "dimension arrow size, before DIMSCALE"),
    "DIMLUNIT": (int, 1, 6, "dimension units: 1 scientific, 2 decimal, 3 engineering, 4 architectural, "
                            "5 fractional, 6 Windows desktop"),
    "DIMDEC": (int, 0, 8, "dimension precision"),
    "DIMZIN": (int, 0, 15, "zero suppression in architectural units: 3 shows 14'-0\" and 6\", "
                         "1 shows 14'-0\" and 0'-6\", 0 shows 14' and 6\""),
    "LTSCALE": (float, 0.001, 10_000, "global linetype scale"),
    "LUNITS": (int, 1, 5, "length units: 1 scientific, 2 decimal, 3 engineering, 4 architectural, 5 fractional"),
    "LUPREC": (int, 0, 8, "length display precision"),
    "INSUNITS": (int, 0, 21, "drawing units (1 inches, 4 millimeters, ...)"),
    "TEXTSIZE": (float, 0.001, 10_000, "default text height"),
}


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
def set_drawing_variables(variables: dict[str, float], name: str = "") -> dict:
    """Change drawing settings saved in the drawing, e.g. {"DIMSCALE": 24, "DIMLUNIT": 4,
    "LUNITS": 4, "LTSCALE": 12} for a 1/2"=1'-0" architectural drawing. DIM* values are
    also copied into the active dimension style, and model space dimensions on that style
    are rebuilt with them. One undo step; restored if any value fails.

    Allowed: DIMSCALE, DIMTXT, DIMASZ, DIMLUNIT, DIMDEC, DIMZIN, LTSCALE, LUNITS, LUPREC, INSUNITS, TEXTSIZE.

    Args:
        variables: name -> new value.
        name: which open drawing (default: active).
    """
    if not variables:
        raise AcadError("Give at least one variable.")
    values = {}
    for var, value in variables.items():
        key = var.strip().upper()
        if key not in VARIABLES:
            raise AcadError(f"{var} is not one of {', '.join(VARIABLES)}.")
        kind, low, high, meaning = VARIABLES[key]
        number = kind(value)
        if kind is int and number != value:
            raise AcadError(f"{key} must be a whole number ({meaning}).")
        if not low <= number <= high:
            raise AcadError(f"{key} must be between {low} and {high} ({meaning}).")
        values[key] = number
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
            # Existing dimensions keep the picture they were built with until each one is
            # updated; REGEN alone does not rebuild them (verified 2026-10-29).
            rebuilt = 0
            for ent in model_space(doc):
                if "Dimension" in str(ent.ObjectName) and str(ent.StyleName) == str(style.Name):
                    ent.Update()
                    rebuilt += 1
            doc.Regen(1)  # acAllViewports
            result["dimension_style_updated"] = str(style.Name)
            result["dimensions_rebuilt"] = rebuilt
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
