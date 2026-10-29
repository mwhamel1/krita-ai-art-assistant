# Architecture

AI Art Assistant is a Krita Python docker (side panel). There is no separate server. The plugin talks to Krita on the UI thread and sends pictures to OpenAI from a background thread.

## Pipeline

```
visible canvas capture
        +
selection stencil (optional, inverted for OpenAI)
        |
        v
HTTPS POST /v1/images/edits  (one click, one image)
        |
        v
candidate preview
        |
        v
new Krita paint layer if you Apply (undoable)
```

The OpenAI mask is guidance. This version does not yet clip applied pixels to the selection.

## Modules

| Piece | Role | Status |
|---|---|---|
| Plugin bootstrap (`__init__.py`, `.desktop`) | Register the docker with Krita | Phase 0 |
| Panel (`docker.py`) | Document info, export, import, Generate, preview | Phase 2 |
| Krita document adapter (`krita_document.py`) | Projection, selection, layer insert | Phase 1 |
| Image pipeline (`image_pipeline.py`) | PNG size checks, coverage, OpenAI mask invert | Phase 2 |
| Prompts (`prompts.py`) | Base prompt + rules + instruction | Phase 2 |
| Credentials (`credentials.py`) | Windows Credential Manager / session key | Phase 2 |
| Settings (`settings.py`) | Non-secret defaults in AppData JSON | Phase 2 |
| OpenAI adapter (`openai_provider.py`) | Stdlib HTTPS Image Edit | Phase 2 |
| Strict selection composite | Clip applied pixels to the stencil | Phase 3 |

## Development install

`scripts/link_plugin_for_dev.ps1` creates a Windows junction from `%APPDATA%\krita\pykrita\ai_art_assistant` to this repo's `ai_art_assistant` folder, and a file link for `ai_art_assistant.desktop`. Restart Krita after code changes.

## What this repo will not include

API keys, `.kra` documents, or game artwork.
