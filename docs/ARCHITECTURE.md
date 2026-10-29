# Architecture

AI Art Assistant is a Krita Python docker (side panel). There is no separate server in the first versions. The plugin talks to Krita on the UI thread and will later send pictures to OpenAI from a background job.

## Pipeline

```
visible canvas capture
        +
selection stencil (optional)
        |
        v
local composite (keep unselected pixels unchanged)  [not in this version]
        |
        v
new Krita paint layer (undoable)
```

The cloud model is guidance only. The plugin is responsible for not applying pixels outside the selection (later version). Phase 1 imports the PNG as a full overlay layer.

## Modules (current and planned)

| Piece | Role | Status |
|---|---|---|
| Plugin bootstrap (`__init__.py`, `.desktop`) | Register the docker with Krita | Phase 0 |
| Panel (`docker.py`) | Document info, export, import, preview | Phase 1 |
| Krita document adapter (`krita_document.py`) | Projection, selection, layer insert | Phase 1 |
| Image pipeline (`image_pipeline.py`) | PNG size checks, coverage stencil | Phase 1 |
| OpenAI adapter | Image Edit HTTPS calls | Phase 2 |
| Job coordinator | One paid request per click, ignore stale results | Phase 2–3 |
| Strict selection composite | Clip applied pixels to the stencil | Phase 3 |

## Development install

`scripts/link_plugin_for_dev.ps1` creates a Windows junction from `%APPDATA%\krita\pykrita\ai_art_assistant` to this repo's `ai_art_assistant` folder, and a file link for `ai_art_assistant.desktop`. Restart Krita after code changes.

## What this repo will not include

API keys, `.kra` documents, or game artwork.
