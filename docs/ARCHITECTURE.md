# Architecture

AI Art Assistant is a Krita Python docker (side panel). There is no separate server in the first versions. The plugin talks to Krita on the UI thread and will later send pictures to OpenAI from a background job.

## Pipeline

```
visible canvas capture
        +
selection stencil (optional)
        |
        v
local composite (keep unselected pixels unchanged)
        |
        v
new Krita paint layer (undoable)
```

The cloud model is guidance only. The plugin is responsible for not applying pixels outside the selection.

## Modules (current and planned)

| Piece | Role | Status |
|---|---|---|
| Plugin bootstrap (`__init__.py`, `.desktop`) | Register the docker with Krita | Phase 0 |
| Panel (`docker.py`) | Show document info and user actions | Phase 0 (read-only) |
| Krita document adapter | Projection, selection, layer insert | Phase 1 |
| Image pipeline | PNG, mask alpha, compositing | Phase 1–3 |
| OpenAI adapter | Image Edit HTTPS calls | Phase 2 |
| Job coordinator | One paid request per click, ignore stale results | Phase 2–3 |

## Development install

`scripts/link_plugin_for_dev.ps1` creates a Windows junction from `%APPDATA%\krita\pykrita\ai_art_assistant` to this repo's `ai_art_assistant` folder, and a file link for `ai_art_assistant.desktop`. Restart Krita after code changes.

## What this repo will not include

API keys, `.kra` documents, or game artwork.