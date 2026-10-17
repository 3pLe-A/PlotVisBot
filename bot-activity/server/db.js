// SQLite store: one row per saved plot (text only, no images), deleted after the retention period.

import { DatabaseSync } from "node:sqlite";
import { randomBytes } from "node:crypto";

export class Store {
  constructor(path, retentionDays = 30) {
    this.db = new DatabaseSync(path);
    this.retentionMs = retentionDays * 86_400_000;
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS plots (
        id         TEXT PRIMARY KEY,
        user_id    TEXT,
        channel_id TEXT,
        lang       TEXT NOT NULL,
        prompt     TEXT NOT NULL,
        state_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS plots_updated ON plots(updated_at);
    `);
  }

  save({ id, userId, channelId, lang, prompt, state }) {
    const now = Date.now();
    const plotId = id || randomBytes(6).toString("hex");
    const existing = id && this.get(id);
    if (existing) {
      this.db.prepare("UPDATE plots SET state_json = ?, updated_at = ? WHERE id = ?").run(JSON.stringify(state), now, id);
    } else {
      this.db.prepare("INSERT INTO plots VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        .run(plotId, userId ?? null, channelId ?? null, lang, prompt, JSON.stringify(state), now, now);
    }
    return plotId;
  }

  get(id) {
    const row = this.db.prepare("SELECT * FROM plots WHERE id = ?").get(id);
    return row ? { ...row, state: JSON.parse(row.state_json) } : null;
  }

  purgeExpired() {
    return this.db.prepare("DELETE FROM plots WHERE updated_at < ?").run(Date.now() - this.retentionMs).changes;
  }
}
