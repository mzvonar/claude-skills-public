# The design and UX bar

Read before building a new surface; skim before reporting any round. The repo's own design system and conventions
win over anything here: this is what to do where they are silent.

## Contents
1. Start from what exists
2. Hierarchy and layout
3. Type, colour and icons
4. States
5. Interaction
6. Copy
7. Accessibility
8. Phone and responsive
9. Motion
10. What makes a UI look generated

## 1. Start from what exists
- Find the design system before drawing: tokens or theme variables, the component library, the icon set, the spacing
  and type scales. Use them; extend them (a new token) before bypassing them (a one-off value).
- Find the closest existing example of what you are making (another card, another list row, another destructive
  action) and match it unless there is a reason not to — then say the reason.
- Prefer the library's component to a hand-built one; wrap it rather than editing a vendored copy.

## 2. Hierarchy and layout
- One primary action per view, visibly primary. Secondary actions quieter; destructive ones apart from the primary.
- Squint test: the most important thing is the most visible. Size, weight, colour and space make hierarchy; boxes and
  borders rarely do.
- One spacing scale. Related things closer together than unrelated ones. Generous outer padding, tighter inner.
- Align to a few edges. Every new left edge is visual noise.
- Unobtrusive means: small, muted, at the edge, revealed when needed — not hidden. A control the user must hunt for is
  a missing control.

## 3. Type, colour and icons
- Two or three type sizes per view, from the scale. Weight for emphasis before size; avoid all-caps paragraphs.
- Comfortable line length (roughly 45–90 characters) and line height (around 1.4–1.6 for body text).
- Colour carries meaning (status, danger, selection) consistently across the app; never colour alone — pair it with
  text or an icon.
- Icons from the app's set, one size and stroke per context, with a text label or an accessible name. An icon that
  needs a tooltip to be understood probably wants a word.

## 4. States
Design all the ones the change can reach, not just the happy path:
empty · loading (skeletons for content, a pending state on the control the user pressed) · error (what happened, what
to do) · one item · many items · long text · disabled (and why) · hover · focus · pressed · selected · offline or
slow, when relevant.

## 5. Interaction
- A control the user waits on shows that it is working, and cannot be pressed twice.
- Destructive or irreversible actions confirm (inline, in the page's style) or offer undo. Say what will happen in
  the confirm, in plain words.
- Keep people in place: after an action, focus and scroll stay where they were or move somewhere obvious.
- Nothing essential behind hover only. Keyboard: everything reachable, in a sensible order, with a visible focus ring.
- Forms: labels (not just placeholders), errors next to the field, the input type that brings up the right keyboard.

## 6. Copy
- Short, concrete, in the product's own words; sentence case; the verb on the button says what happens ("Remove
  comment", not "OK").
- Empty states say what goes here and how to add the first one.
- Never lorem ipsum in something the user will review; write the real string.

## 7. Accessibility
- Text contrast at least 4.5:1 (3:1 for large text), and 3:1 for icons and control borders that carry meaning.
- Targets at least 24×24 px, 44×44 comfortable on touch; enough space between adjacent targets.
- Every control has an accessible name; images have alt text (empty `alt=""` when decorative).
- Respect `prefers-reduced-motion`; never convey information by motion alone.

## 8. Phone and responsive
- Check at 390 px every round. Content reflows; nothing scrolls sideways unless it is a deliberate scroller.
- Thumb reach: primary actions low and large; nothing important in a corner the thumb cannot reach.
- Safe areas (notch, home indicator) respected for fixed elements; a floating control does not cover the last row.
- Tables and wide content: a scroll container with a visible cue, or a stacked layout.

## 9. Motion
- Small and fast (around 150–250 ms), easing out; it explains a change (where something went), it never decorates.

## 10. What makes a UI look generated
Avoid, unless the design system asks for it: gradients and glows for their own sake; emoji used as icons; everything
in a rounded, shadowed card; every element centred; uniform giant radii; decorative illustrations or fake logos and
photos (use an honest placeholder box with a label); filler stats and badges; three-column feature grids by reflex;
inconsistent icon styles. Restraint and consistency read as designed.
