# Database Schema

The service uses one relational table, accessed through SQLAlchemy 2.x. Production runs on
**PostgreSQL (Neon)**. Local development falls back to **SQLite** when `DATABASE_URL` is unset.

```mermaid
erDiagram
    TRANSCRIPTIONS {
        INTEGER id PK "auto-increment"
        VARCHAR title "max 200, default Untitled"
        TEXT text "full transcript, UTF-8"
        VARCHAR language "max 32"
        FLOAT duration_sec "seconds of audio"
        TIMESTAMPTZ created_at "UTC"
        TIMESTAMPTZ updated_at "UTC"
    }
```

## Table `transcriptions`

| Column | PostgreSQL type | Null | Default | Description |
|---|---|---|---|---|
| `id` | `SERIAL` | no | sequence | Primary key |
| `title` | `VARCHAR(200)` | no | `'Untitled'` | Short label; set to the first 60 chars of the transcript on save |
| `text` | `TEXT` | no | `''` | Full transcript (Devanagari and Latin script) |
| `language` | `VARCHAR(32)` | no | `'auto'` | Most frequent detected language (`hi`, `en`, …) |
| `duration_sec` | `DOUBLE PRECISION` | no | `0` | Length of the recorded audio |
| `created_at` | `TIMESTAMPTZ` | no | now (UTC) | Insert time |
| `updated_at` | `TIMESTAMPTZ` | no | now (UTC) | Last update time (ORM `onupdate`) |

Defaults are applied by the ORM. This DDL is the PostgreSQL equivalent of what
`Base.metadata.create_all()` creates, with the defaults written out:

```sql
CREATE TABLE transcriptions (
    id            SERIAL PRIMARY KEY,
    title         VARCHAR(200)      NOT NULL DEFAULT 'Untitled',
    text          TEXT              NOT NULL DEFAULT '',
    language      VARCHAR(32)       NOT NULL DEFAULT 'auto',
    duration_sec  DOUBLE PRECISION  NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ       NOT NULL DEFAULT now()
);
```

## ORM model (`app/db.py`)

```python
class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled")
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(32), default="auto")
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
```

## Queries used by the API

| Operation | SQL (simplified) |
|---|---|
| List | `SELECT * FROM transcriptions ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset` |
| Search | `… WHERE text ILIKE :pattern OR title ILIKE :pattern` (pattern = `%q%`) |
| Read | `SELECT * FROM transcriptions WHERE id = :id` |
| Create | `INSERT INTO transcriptions (title, text, language, duration_sec, created_at, updated_at) VALUES (…) RETURNING id` |
| Update | `UPDATE transcriptions SET title = :title, …, updated_at = :now WHERE id = :id` |
| Delete | `DELETE FROM transcriptions WHERE id = :id` |

## Example rows

| id | title | text | language | duration_sec |
|---|---|---|---|---|
| 1 | मेरा नाम काशी है… | मेरा नाम काशी है और मैं Bangalore में software engineer हूँ | hi | 6.56 |
| 2 | Kal subah meeting hai… | Kal subah meeting hai, please slides ready rakhna. | hi | 4.12 |
| 3 | Project update | The deployment is live on Hugging Face. | en | 3.20 |

## Connection configuration

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host/db?sslmode=require` | Unset or empty → `sqlite:///./transcriptions.db` |

`app/db.py` normalises the URL before connecting:
- strips whitespace and surrounding quotes;
- rewrites `postgres://` and `postgresql://` to `postgresql+psycopg2://`;
- removes Neon's `channel_binding=require` (`sslmode=require` still enforces TLS);
- enables `pool_pre_ping`, so connections dropped when Neon autosuspends are replaced.

`GET /api/health` reports the active backend: `"database": "postgresql"` or `"sqlite"`.

## Future improvements

- Alembic migrations instead of `create_all`.
- A `pg_trgm` GIN index on `text` for fast `ILIKE` search at scale.
- A `user_id` foreign key once authentication is added.
