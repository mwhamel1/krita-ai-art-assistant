# Krita AI Art Assistant

A **Krita Python plugin** for artist-controlled image editing. You sketch or paint in Krita, optionally select a region, and later versions will request an AI edit. The result comes back as a **new layer**. Original layers are not overwritten.

This is a public-source production tool, not a commercial product. Recruiters do not need to install Krita to read this page. A walkthrough video will be linked here when it exists.

**Pinned Krita version:** 5.3.4.1 for Windows (`C:\Program Files\Krita (x64)\`).

## How it is supposed to work

1. Capture the **visible canvas** (what Krita is showing, not a screenshot and not only one layer).
2. Capture the current **selection** as a full-size stencil when you are editing part of the image.
3. **Composite** so applied pixels stay inside that selection, even if the model changes more than it should.
4. Insert the result as a **new undoable layer**.

```
sketch in Krita -> panel -> visible picture + selection stencil
                 -> (later) cloud image edit
                 -> new layer, originals kept
```

## Implemented / Not yet

**Implemented (Phase 0)**

- Krita docker named **AI Art Assistant**
- Shows the open document name and pixel size
- Shows whether a selection exists (and its bounds)
- Refresh button, plus updates when you switch documents

**Not yet**

- Export the visible canvas to a PNG
- Export the selection stencil
- Import a PNG as a new layer
- OpenAI Image Edit / Generate
- Walkthrough video and docker screenshot

The Generate button is visible and disabled on purpose so the panel is honest.

## Install (Windows, Krita 5.3.4.1)

Krita does not load plugins from this GitHub folder by itself. It loads them from:

`C:\Users\<you>\AppData\Roaming\krita\pykrita\`

### Development link (this computer)

1. Close Krita if it is open.
2. In PowerShell, from this repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\link_plugin_for_dev.ps1
```

3. Open Krita.
4. **Settings → Configure Krita → Python Plugin Manager**
5. Check **AI Art Assistant**. If you see an error next to it, the plugin failed to load (see troubleshooting).
6. Click OK, then **close and reopen Krita**.
7. **Settings → Dockers → AI Art Assistant** if the panel is not visible.

### What you should see

- A side panel titled **AI Art Assistant**
- With no drawing open: `Document: No document open.`
- With a drawing open: the file name and size, for example `1024 × 1536`
- After you make a selection: `Selection: Yes` and a size
- Export / Import / Generate buttons greyed out

## Troubleshooting

- The plugin is unchecked after restart: it crashed while loading. In Krita open **Help → Show Krita Log for Bug Reports** and look for `ai_art_assistant`.
- The panel name is missing from Dockers: the Python Plugin Manager checkbox is off, or Krita was not restarted after enabling it.
- Document labels stay empty: click **Refresh**, or click the drawing once so it is the active document.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Plugin code lives in `ai_art_assistant/`. Krita discovers it through `ai_art_assistant.desktop`.

## License

MIT. See [LICENSE](LICENSE).