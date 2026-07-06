# Storage: the Source Abstraction

## Goal

Decouple "where tuples come from" from the algebra. Today `Relation` *is* an
in-memory frozenset and the loader knows only CSV + workspace JSON. This
design introduces a `Source` protocol so that:

1. New file formats (Parquet, JSON, TSV) plug in without touching the executor.
2. Schemas persist alongside data and re-apply automatically on load.
3. Joins against large loaded files can use persistent indexes.
4. Pipelines whose prefix is filter/project can stream files larger than memory.
5. Storage backends can eventually live in separate repos.

Non-goals (explicitly): column-vectorized execution, MVCC/concurrent writers,
network/remote backends. The algebra stays tuple-at-a-time and immutable.

## 1. The Source protocol

```python
class Source(Protocol):
    """Anything that can yield tuples into the algebra."""

    def __iter__(self) -> Iterator[Tuple_]: ...
    @property
    def attributes(self) -> frozenset[str]: ...
    @property
    def schema(self) -> dict[str, str]: ...          # always a dict; str default
    def materialize(self) -> Relation: ...            # collapse to in-memory
    def join_index(self, attrs: frozenset[str]) -> JoinIndex | None: ...
        # optional acceleration; None = "build transiently as today"
```

`Relation` implements `Source` trivially (`materialize` returns `self`,
`join_index` returns the transient hash index we already build). All existing
code keeps working because a Relation is a Source.

Two new implementations:

- **`FileSource`** — lazy: holds a path + format adapter; `__iter__` streams
  rows from disk, parsing tuples on the fly. `materialize()` reads everything
  once and memoizes the resulting Relation (subsequent use is free, and pins
  a consistent snapshot — the file changing on disk mid-session can't produce
  two different answers for the same bound name).
- **`StreamSource`** — a lazy transformation wrapper: `FilterStream(src, pred)`,
  `ProjectStream(src, attrs)`, etc. One-pass, no storage.

### Eager by default, lazy by request

`\load file.csv` stays **eager** (materializes immediately) — identical
behavior to today, no surprises. Laziness is opt-in:

```
\load big.csv --lazy          # binds a FileSource; nothing read yet
codd big.csv+lazy -e "..."    # CLI spelling
```

A lazy binding materializes (and memoizes) the first time an operator that
needs the whole relation touches it. Until then, a chain like
`big ? x > 1 # [a b]` streams: constant memory regardless of file size.

### Which operators stream

| Streams (tuple-at-a-time)            | Materializes input               |
|--------------------------------------|----------------------------------|
| `?` `?!` filter                      | `$` sort, `^` take-after-sort    |
| `#` `#!` project/remove¹             | `/.` `/*` summarize/broadcast    |
| `+:` `=:` extend/modify              | `|.` `-.` `&.` set ops           |
| `@` rename                           | `/^` rank, `/&` bucket           |
| `/>` split, `<:` unnest              | `?.` describe                    |
| `*.` `*<` **probe side**²            | `*.` `*<` `*:` **build side**    |

¹ Projection dedup requires a seen-set — memory grows with *output*
cardinality, not input size. Acceptable; document it.
² Joins materialize the smaller/right side into the hash index and stream the
left through it. This is the classic build/probe split and it means
`bigfile ? pred *. smalldim` never holds bigfile in memory.

The executor changes are mechanical: `_as_relation(node)` becomes
`_as_source(node)` for streaming-safe operators, and `.materialize()` is
called exactly where a frozenset is genuinely required. Phase 1 can land the
protocol with zero behavior change (everything still materializes), then
streaming is enabled operator-by-operator.

## 2. Loading and format detection

### Format registry

```python
@dataclass
class Format:
    name: str                                  # "csv", "workspace", "parquet"
    extensions: tuple[str, ...]                # (".csv",), (".codd",), ...
    sniff: Callable[[Path], bool]              # content check, cheap
    open: Callable[[Path, LoadOptions], Source]

FORMATS: list[Format] = [WORKSPACE, CSV, TSV, ...]   # priority order
```

Resolution order for `\load path`:

1. **Explicit override wins:** `\load file.dat --format=csv`.
2. **Extension match:** `.csv` → csv, `.tsv` → tsv, `.parquet` → parquet,
   `.codd` → workspace, `.json` → json.
3. **Content sniff** (for extensionless files, stdin dumps, `.dat`):
   run each format's `sniff` in priority order. Workspace already sniffs
   (JSON with `version`+`relations`); CSV sniffs by "first line splits on
   the delimiter into >0 fields and contains no NUL bytes"; Parquet by the
   `PAR1` magic bytes.
4. Nothing matches → error listing formats tried.

This replaces the current hardcoded `is_workspace_file(path) → else CSV`
branch in `_cmd_load` with a loop over the registry. Stdin (`\load -`) skips
extension matching and goes straight to sniffing the buffered first block.

Third-party formats register via Python entry points
(`[project.entry-points."codd.formats"]`), which is the seam for the
separate-repo story: `codd-parquet` is a pip package that registers a
`Format`; codd core never imports pyarrow.

### LoadOptions

The existing per-load flags (`--genkey`, `+key=`, `+uuid=`, `+hash=`,
`:: Schema`, alias) collect into one `LoadOptions` dataclass passed to
`Format.open`, instead of the current five parallel keyword args threaded
through three call sites. Generated columns (key/uuid/hash) are applied by a
wrapper source so each format doesn't reimplement them.

## 3. Schema persistence (sidecar files)

### The convention

A schema sidecar is **just a codd schema relation, stored as CSV**, named
after the data file:

```
orders.csv            # the data
orders.schema.csv     # attr,type — exactly the {attr type; ...} shape :: uses
```

This is deliberately codd-native: the sidecar is readable by `\load`, is
produced by existing operators, and needs no new file format.

### Applying — automatic

`\load orders.csv` checks for `orders.schema.csv`. If present:

1. Load it as a schema relation (`schema_from_relation`, UDTs resolved
   against the current environment as today).
2. Skip the loader's per-column type inference entirely — coerce straight to
   the declared types. Faster and deterministic.
3. Coercion failure = load failure with a row/column message (this satisfies
   "if the relation cannot be cast to the schema, the load fails").

Opt-out: `\load orders.csv --raw` ignores the sidecar. An explicit
`:: Name` on the load line overrides the sidecar.

### Saving — explicit command, plus it already composes

Writing the sidecar is a one-liner with existing ops:

```
\export orders.schema.csv (orders ::)
```

Add sugar so the convention is discoverable:

```
\schema orders                 # writes orders.schema.csv next to its source
\schema orders path.csv        # explicit target
```

`\schema` needs to know which file a relation was loaded from — `FileSource`
records its origin path; relations built by expressions have none and require
the explicit-path form.

Deliberately **not** automatic-on-`::`: applying a schema in a query should
not silently write files. Persisting a schema is a decision; one short
command is cheap.

## 4. Indexing

### What gets indexed

Persistent **hash indexes on join columns** — the exact structure
`_build_join_index` builds transiently today, written to disk so repeated
sessions don't rebuild it, and so joins against a lazy FileSource can probe
without a full scan.

Range/B-tree indexes are out of scope until there's an optimizer that can
use them.

### File format

```
orders.csv
orders.idx.json        # {version, digest, columns: {"<col>": {bucket: [offsets]}}}
```

- `digest` = (size, mtime, first-4KB hash) of the data file. Mismatch →
  index silently ignored and rebuilt on demand. No invalidation bookkeeping.
- Bucket keys are the `coarse_match_key` tuples with a stable string
  encoding: `("n", Decimal("1.5"))` → `"n:1.5"`, `("d", date)` → `"d:2026-01-01"`,
  `("s", s)` → `"s:" + s`. The same over-grouping guarantee applies; probes
  still verify candidates with `Tuple_.matches`, so correctness never
  depends on the index.
- Offsets are byte offsets of row starts in the CSV (row-group/row indexes
  for Parquet).

### Creating and using

```
\index orders name          # build orders.idx.json bucket map for "name"
\index orders [a b]         # composite key
```

Executor hook — one seam, already designed for it:

```python
index = right.join_index(shared) or build_transient_index(right, shared)
```

`Relation.join_index` returns None (transient build, exactly today's path).
`FileSource.join_index` loads the sidecar if digest-valid and the column set
matches, and returns a probing wrapper that seeks+parses only candidate rows.

The payoff case: `small_rel *. big_lazy_file` with an index on the join key
reads only matching rows of the big file. Without the index, lazy join still
works (single streaming pass to build the transient index) — the sidecar
just makes repeat queries cheap.

### Non-feature: automatic index creation

Codd never creates an index implicitly. `\index` is a user decision, like
`\schema`. (A future `\ops`-style hint that a repeated slow join *could* use
one is fine; magic writes to disk are not.)

## 5. Writes and atomicity

- Every file codd writes (`\save`, `\export`, `\schema`, `\index`) goes
  through write-to-temp + `os.replace` — atomic on POSIX, no torn files.
- Codd's data model is immutable rebind, so there is no in-place row update
  and therefore no write-ahead-log/MVCC requirement. If a multi-process
  scenario ever appears, revisit; do not build for it now.

## 6. Environment changes

`Environment._bindings` becomes `dict[str, Source]` (Relations are Sources,
so existing bindings are unchanged). Two behavioral notes:

- `\env` shows lazy bindings distinctly: `orders: lazy csv (orders.csv), schema: 6 cols`
  — row count unknown until materialized, so don't print one.
- `\save` (workspace) **materializes** lazy sources before serializing —
  a workspace file remains a self-contained snapshot.

## 7. Phasing

Each phase lands independently with the full suite green:

1. **Protocol + conformance.** `Source` protocol; `Relation` conforms;
   `Environment` holds Sources; executor calls `materialize()` everywhere.
   Zero behavior change.
2. **Format registry.** Move workspace-vs-CSV detection into the registry;
   add `--format` override and content sniffing; collect `LoadOptions`.
3. **Schema sidecars.** Auto-apply on load, `--raw` opt-out, `\schema` command,
   load-fails-on-coercion-error.
4. **Lazy CSV.** `--lazy` / `+lazy`; streaming filter/project/extend prefix;
   build/probe join split; memoized materialization.
5. **Parquet read** (separate package `codd-parquet` via entry point).
6. **Persistent indexes.** `\index`, sidecar format, `join_index` hook.

The separate-repo split happens after phase 5 proves the entry-point seam:
core keeps `Source`, the registry, csv+workspace built-ins; everything else
is a plugin.

## Open questions

1. **Lazy dedup semantics.** A CSV with duplicate rows materializes to a
   smaller relation (set semantics). A streaming filter over the same file
   sees duplicates and passes each through, but downstream materialization
   dedups. Result cardinality is identical either way; row-count *messages*
   during load may differ. Probably fine — confirm.
2. **Sidecar naming.** `orders.schema.csv` vs `.orders.schema` vs a
   `.codd/` subdirectory for all sidecars (schema + index). Flat siblings
   are more discoverable; a subdirectory pollutes less. Leaning flat.
3. **`\load dir/`** — load every recognized file in a directory as its stem?
   Cheap to add once the registry exists; deferred until wanted.
