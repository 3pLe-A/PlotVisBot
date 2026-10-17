import { test, after } from "node:test";
import assert from "node:assert/strict";

process.env.PLOTBOT_DB = ":memory:";
delete process.env.ANTHROPIC_API_KEY;
const { app } = await import("../server/index.js");
const server = app.listen(0);
const base = `http://127.0.0.1:${server.address().port}`;
after(() => server.close());

const post = (path, body) => fetch(`${base}${path}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

test("config reports natural language off without a key", async () => {
  assert.deepEqual(await (await fetch(`${base}/api/config`)).json(), { naturalLanguage: false });
});

test("translate is refused without a key", async () => {
  assert.equal((await post("/api/translate", { prompt: "a sphere" })).status, 503);
});

test("save and load a plot", async () => {
  const state = { math: "y = sin(k x)", explanation: "", params: { k: 2 }, ranges: { x: [0, 3] } };
  const { id } = await (await post("/api/plots", { lang: "ru", prompt: "y = sin(k x)", state })).json();
  assert.match(id, /^[0-9a-f]{12}$/);
  const row = await (await fetch(`${base}/api/plots/${id}`)).json();
  assert.deepEqual(row.state, state);
  assert.equal(row.lang, "ru");
  assert.equal((await fetch(`${base}/api/plots/000000000000`)).status, 404);
});

test("pending prompt requires a Discord token", async () => {
  assert.equal((await fetch(`${base}/api/pending`)).status, 401);
});
