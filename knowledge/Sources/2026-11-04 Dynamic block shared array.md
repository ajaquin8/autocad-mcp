# 2026-11-04 Dynamic block shared array

Report-IDs: AMCP-LIVE-20261104-01 to AMCP-LIVE-20261104-03 (one series)
Writer: Claude Code. The batch was described first and run after Alex's go ("Saved, go"). Alex was at the machine, and twice cleared a stuck prompt with Esc.
Question: the screw block from [[Sources/2026-11-03 Dynamic block authoring]] kept the threads of the size it was first worked out at when only the size changed (user-reported, with screenshots). Can it be rebuilt so a size change always redraws the threads?

## Background (research pass, before the rebuild)
- **verified** (read from DXF copies of the files, using the console engine): the user's existing screw block does not have the fault. It has **one** thread array whose source objects show in every screw visibility state. A size lookup drives a width parameter, and stretches widen the thread and head from it.
- **verified:** AutoCAD 2026's own sample fastener blocks (`Sample\en-us\Dynamic Blocks\Mechanical - Imperial.dwg`: shoulder screw, hex bolt, anchor rod) use no array action for threads at all. They use simplified lines that stretch, or a separate length parameter per size.
- **inferred:** the faulty block hid a different thread unit and array in each visibility state. The arrayed copies are made when the block is worked out, and they are not in the visibility lists. So a change of visibility alone leaves copies from the earlier size. A community post reports the same "bleed-over" with arrays and visibility states (forum, not Autodesk documentation).

## The rebuild
- **One shared thread unit** (two zigzags and a crest line, at one schematic pitch for every size), visible in every state, with **one array**.
- **Visibility states** hold only each size's head, washer and drill point.
- **A Size lookup** (7 rows, reverse lookup) sets the visibility and three hidden linear helpers:
  - Major and Minor (base point at the midpoint), which stretch the zigzag's outer and inner points;
  - Pilot, which stretches the thread end.
- Every size has a different outside diameter, so any size change changes Major, and AutoCAD re-works the whole block.
- **Length** stretches the drill points, the thread end and the Pilot helper. The Thread parameter is chained to the array.

## Results
- **01, the build script.**
  - **First build: wiring faults.** It ran without errors, but reading the saved file offline found three faults:
    - the Length and Pilot stretches were attached to their parameters' **base** points;
    - the attributes were hidden in every state.
  - **Two further runs stopped at "Select parameter:":**
    - once because the pick point was off screen;
    - once because it fell in the empty gap between the arrows of a short dimension.

    Each time, AutoCAD refused automation until someone pressed Esc.
  - **One run lost its first COM calls** to a third-party add-in that loads into every new drawing.
  - **Sixth run: 38/38,** after these fixes:
    - naming the parameter point;
    - a fixed zoom window;
    - picking on label text;
    - waiting for the new drawing to settle.
- **01, by hand (desktop control):**
  - the attributes position-locked, then shown in every state;
  - the lookup table (7 rows, audit clean);
  - *Show properties = No* on the helpers.
- **02, test of the authoring file in a new drawing.**
  - **First run: 85 passed, many failed.** Changing only the size gave the right drill point, root diameter and thread count for every size, but:
    - the outside diameter was wrong, because the left Minor stretch's frame missed the zigzag's inner points, so AutoCAD moved the objects instead;
    - any length change put the threads about 0.75" past the tip, because Pilot was chained and its stretch moved the thread end a second time;
    - the default size read "Custom";
    - the label showed `####`.
  - **Fixes, by hand:**
    - Pilot chain off;
    - the left Minor stretch rebuilt;
    - #12-14 moved to the top of the states;
    - the Size lookup shown in every state;
    - the label field remade in the Field dialog.
  - **Rerun: 167/168.** The one miss was a final zoom call refused while AutoCAD was busy, not a block check.
- **03, the same test on the released library file** (written out with WBLOCK on a copy by the console engine): **169/169**. The checks:
  - changing only the size, for every size: washer, outside and root diameter, tip, thread count, and threads ending above the drill point;
  - size then length, and length then size;
  - six switches between sizes, including two pairs with the same drill length;
  - the label text after a regen;
  - the default size, and only Size and Length shown.

## Not covered
- Scales other than full size; a plan or head view; other fastener families.
- The block's look at one schematic pitch was chosen by the user, not tested against a drawing standard.
- No server code changed. The block, its data and the scripts are the user's and stay outside this repository.

## Correction to [[Sources/2026-11-03 Dynamic block authoring]] (inferred, 2026-11-04)
- **Run 11's "the length grip moved nothing":** that note blamed parameters hidden in the visibility states. The faulty block's leftover scripted stretch is also attached to the Length parameter's *base* point. An empty answer to "parameter point" takes the point nearest the pick, and that pick was nearer the base. So both causes were probably present.
- **Runs 12 and 13 always set Length after the size.** That hid the stale-thread fault, which the user found on 2026-11-04.

## Process notes
- Desktop control stops whenever another window comes forward. Once, clicking AutoCAD's taskbar button minimised it, because it already counted as the active window.
- PowerShell 5.1 strips the double quotes from arguments passed to a native program, which broke AutoLISP sent that way. Sending through Git Bash kept them.
