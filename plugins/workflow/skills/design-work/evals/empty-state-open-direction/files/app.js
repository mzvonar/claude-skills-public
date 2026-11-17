// The inbox's documents. Empty for a new organisation: ?demo=1 fills it with sample rows.
const documents =
  new URLSearchParams(location.search).get("demo") === "1"
    ? [
        { name: "Invoice 2026-118 — Example Supplies", from: "forwarded by e-mail", when: "today" },
        { name: "Receipt — Corner fuel station", from: "uploaded by a client", when: "yesterday" },
      ]
    : []

const list = document.getElementById("list")
for (const d of documents) {
  const li = document.createElement("li")
  li.innerHTML = `<span>${d.name}</span><span class="meta">${d.from} · ${d.when}</span>`
  list.append(li)
}
