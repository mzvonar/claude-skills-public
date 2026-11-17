# Reading the screenshots

The lint in `visual-check.mjs` finds what geometry can prove. Everything below needs an eye. Open each PNG and go
through the list for the surfaces you touched; it takes a minute and catches what users notice first.

## Layout
- Nothing scrolls sideways at 390 px, and nothing is cut at the right edge.
- Edges line up: text starts on the same left edge as its siblings; a right-aligned control lines up with the other
  right-aligned controls; icons sit on the text's centre line, not its top.
- The thing you added did not push something onto its own line, and no row grew taller than its siblings.
- Spacing follows a rhythm: the same gap between the same kind of things; a group is tighter inside than between
  groups. One odd 3 px gap reads as a bug.
- Nothing floats over content it should not (a fixed button over the last row, a popover off-screen, a sticky header
  covering an anchor target).

## Consistency with the neighbours
- Same control, same look: size, colour, weight, radius, icon, hover. If the user said "like X", put the two side by
  side and compare at the same zoom.
- Type: the sizes and weights in use belong to the page's scale; no new size for one label.
- Colour: from the palette or tokens; muted things muted the same way as other muted things.
- Icons: from the same set, the same stroke and size as the icons around them.

## Content and states
- Long text: a long name, a long word, a two-line note. Does it wrap, truncate with an ellipsis, or break the row?
- No data and too much data: the empty state, one item, many items.
- Loading and error states, when the change touches them.
- The control in each state you can reach: hover (desktop), focus (keyboard: a visible ring), pressed, disabled,
  selected.

## Phone (390 px)
- Every control comfortable to tap (44 px is comfortable; the lint flags under 24) and far enough from its neighbour.
- Nothing depends on hover; a tooltip-only label has another way in.
- Text readable without zoom (body around 14–16 px); nothing under the notch or the home bar.

## Before / after
For a fix to something the user saw, shoot before the edit (`--label before`) and after (`--label after`) and look at
the pair: the fix landed, and nothing else on the screen moved.

## What the lint reports, and its blind spots
| Kind | Means | Blind spot |
|---|---|---|
| `horizontal-overflow` | the page is wider than the viewport; names the widest element | a container that scrolls on purpose is skipped |
| `clipped-text` | text cut by `overflow: hidden` without an ellipsis | text cut by a fixed height on a parent that is not the text's own box |
| `overlapping-text` | two text boxes intersect | text over an image or icon |
| `overlapping-controls` | two controls intersect | a control under a fixed/sticky element (skipped) |
| `small-target` | a control under 24 px at phone width | inline links in running text (skipped, as WCAG allows) |
| `low-contrast` | text below 4.5:1 (3:1 for large text) on its nearest opaque background | text over an image or gradient |
| `unnamed-control` / `image-without-alt` | no accessible name | a name that is present but meaningless |
| console / page errors, HTTP ≥ 400 | what the page logged while loading | errors that happen only after an interaction — drive it and re-check |

The lint never says "it looks good". Only you can, after looking.
