// design-work's visual check: the layout lint and the argument parser, under node with no browser.
//
// The lint is what turns "I took a screenshot" into "I would have noticed": each rule below is one way a page breaks
// while every unit test stays green — sideways scrolling on a phone, text cut off or drawn over other text, two
// controls under one thumb, a target too small to hit, text too faint to read, a control a screen reader cannot name.

import assert from "node:assert/strict";
import path from "node:path";
import { describe, it } from "node:test";
import { pathToFileURL } from "node:url";

const V = await import(pathToFileURL(path.join(import.meta.dirname, "..", "skills", "design-work", "scripts", "visual-check.mjs")).href);

const box = (over) => ({ id: 0, sel: "div", x: 0, y: 0, w: 100, h: 20, interactive: false, inlineLink: false, ownText: false,
  text: "", clipsX: false, clipsY: false, ellipsis: false, color: null, bg: null, fontSize: 14, fontWeight: 400,
  position: "static", name: null, img: null, inScroller: false, ...over });
const kinds = (issues) => issues.map((i) => i.kind);

describe("parseArgs", () => {
  it("defaults to a desktop and a phone width", () => {
    const o = V.parseArgs(["http://localhost:3000/x"]);
    assert.deepEqual(o.widths, [1280, 390]);
    assert.equal(o.lint, true);
  });
  it("reads every option", () => {
    const o = V.parseArgs(["u", "--widths", "1440,768,390", "--out", "d", "--label", "after", "--selector", ".card", "--full",
      "--wait", "50", "--header", "X-Token: a:b", "--color-scheme", "dark", "--no-lint"]);
    assert.deepEqual(o.widths, [1440, 768, 390]);
    assert.equal(o.headers["X-Token"], "a:b");
    assert.equal(o.full && !o.lint && o.colorScheme === "dark" && o.label === "after" && o.selector === ".card", true);
  });
  it("refuses no URL, an unknown option and a missing value", () => {
    assert.throws(() => V.parseArgs([]), /URL/);
    assert.throws(() => V.parseArgs(["u", "--zoom", "2"]), /unknown option/);
    assert.throws(() => V.parseArgs(["u", "--out"]), /needs a value/);
  });
});

describe("contrast", () => {
  it("is 21:1 for black on white and 1:1 for a colour on itself", () => {
    assert.equal(V.contrast("rgb(0, 0, 0)", "rgb(255, 255, 255)").toFixed(0), "21");
    assert.equal(V.contrast("rgb(120, 120, 120)", "rgb(120, 120, 120)"), 1);
  });
  it("blends a translucent colour over its background", () => {
    assert.ok(V.contrast("rgba(0, 0, 0, 0.1)", "rgb(255, 255, 255)") < 1.3);
  });
  it("cannot judge a colour it cannot parse", () => {
    assert.equal(V.contrast("var(--x)", "rgb(0,0,0)"), null);
  });
});

describe("lint", () => {
  it("names the element that makes a phone page scroll sideways", () => {
    const issues = V.lint({ vw: 390, sw: 520, items: [box({ sel: "table.wide", w: 520 }), box({ sel: "p" })] }, 390);
    assert.equal(issues[0].kind, "horizontal-overflow");
    assert.equal(issues[0].sel, "table.wide");
  });
  it("does not blame a deliberate horizontal scroller", () => {
    const issues = V.lint({ vw: 390, sw: 390, items: [box({ sel: "pre", w: 900, inScroller: true })] }, 390);
    assert.deepEqual(kinds(issues), []);
  });
  it("flags text cut off without an ellipsis, and accepts a deliberate ellipsis", () => {
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [box({ ownText: true, text: "a long title", clipsX: true })] }, 1280)), ["clipped-text"]);
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [box({ ownText: true, text: "a long title", clipsX: true, ellipsis: true })] }, 1280)), []);
  });
  it("flags text drawn over other text, not text nested in its own box", () => {
    const a = box({ sel: "span.a", ownText: true, text: "one", w: 80, h: 20 });
    const over = box({ sel: "span.b", ownText: true, text: "two", x: 40, y: 5, w: 80, h: 20 });
    const nested = box({ sel: "b", ownText: true, text: "in", x: 10, y: 2, w: 20, h: 16 });
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [a, over] }, 1280)), ["overlapping-text"]);
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [a, nested] }, 1280)), []);
  });
  it("flags two controls under one thumb, but not a fixed control floating over content", () => {
    const b1 = box({ sel: "button.x", interactive: true, name: "Remove", w: 30, h: 30 });
    const b2 = box({ sel: "button.y", interactive: true, name: "Edit", x: 20, y: 10, w: 30, h: 30 });
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [b1, b2] }, 1280)), ["overlapping-controls"]);
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [b1, { ...b2, position: "fixed" }] }, 1280)), []);
  });
  it("flags a small target on a phone only, and never an inline link in running text", () => {
    const x = box({ sel: "span.rm", interactive: true, name: "Remove", w: 12, h: 14 });
    assert.deepEqual(kinds(V.lint({ vw: 390, sw: 390, items: [x] }, 390)), ["small-target"]);
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [x] }, 1280)), []);
    assert.deepEqual(kinds(V.lint({ vw: 390, sw: 390, items: [{ ...x, inlineLink: true }] }, 390)), []);
  });
  it("flags faint text against the large-text threshold where it applies", () => {
    const grey = { ownText: true, text: "muted", color: "rgb(150, 150, 150)", bg: "rgb(255, 255, 255)" };
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [box({ ...grey, fontSize: 14 })] }, 1280)), ["low-contrast"]);
    assert.deepEqual(kinds(V.lint({ vw: 1280, sw: 1280, items: [box({ ...grey, color: "rgb(118, 118, 118)", fontSize: 28 })] }, 1280)), []);
  });
  it("flags a control a screen reader cannot name and an image with no alt", () => {
    const issues = V.lint({ vw: 1280, sw: 1280, items: [box({ sel: "button.icon", interactive: true, name: "", w: 40, h: 40 }), box({ sel: "img", img: { alt: null } })] }, 1280);
    assert.deepEqual(kinds(issues).sort(), ["image-without-alt", "unnamed-control"]);
  });
  it("reports one muted colour used on many labels as one finding, with its count", () => {
    const grey = { ownText: true, color: "rgb(150, 150, 150)", bg: "rgb(255, 255, 255)" };
    const issues = V.lint({ vw: 1280, sw: 1280, items: [box({ ...grey, text: "2h ago" }), box({ ...grey, text: "4h ago", y: 40 }), box({ ...grey, text: "modified", y: 80 })] }, 1280);
    assert.deepEqual(kinds(issues), ["low-contrast"]);
    assert.match(issues[0].detail, /3 texts/);
  });
  it("reports each finding once", () => {
    const t = box({ ownText: true, text: "x", clipsX: true });
    assert.equal(V.lint({ vw: 1280, sw: 1280, items: [t, { ...t, id: 1 }] }, 1280).length, 1);
  });
});
