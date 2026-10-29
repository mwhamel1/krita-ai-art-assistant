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

**Implemented (Phase 1)**

- Krita docker named **AI Art Assistant**
- Shows the open document name, pixel size, and whether a selection exists
- Export the visible canvas to a PNG (hidden layers stay out)
- Export the current selection as a same-size stencil PNG
- Import a PNG as a new undoable layer (originals kept; size must match)
- Preview and **Show exported files**
- Automatic tests for size and stencil coverage (`py -3.14 -m unittest tests.test_image_pipeline`)

**Not yet**

- OpenAI Image Edit / Generate
- Clipping an imported result to the selection (that is a later step)
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
5. Check **AI Art Assistant**. If there is an error next to it, the plugin failed to load (see troubleshooting).
6. Click OK, then **close and reopen Krita**.
7. You should be on the Start screen. **Do not** open **Settings → Dockers** yet; those names stay grey until a drawing exists.
8. Click **New Image** (or **File → New**), then Create.
9. **Settings → Dockers → AI Art Assistant** and check it so the side panel appears.

After any code change, fully restart Krita. Plugins do not live-reload.

### What you should see

- A side panel titled **AI Art Assistant**
- With a drawing open: the file name and size, for example `1024 × 1536`
- After you make a selection: `Selection: Yes` and a size
- **Export visible picture** and **Import as new layer** clickable
- **Export selection stencil** clickable only when a selection exists
- **Generate (not built yet)** greyed out

Exported PNGs go to `%LOCALAPPDATA%\krita-ai-art-assistant\exports\`. Use **Show exported files** to open that folder. Do not put those files, `.kra` files, or game art into git.

## Troubleshooting

- The plugin is unchecked after restart: it crashed while loading. In Krita open **Help → Show Krita Log for Bug Reports** and look for `ai_art_assistant`.
- The panel name is grey in Dockers on the Start screen: create or open an image first, then try Dockers again.
- The panel name is missing from Dockers: the Python Plugin Manager checkbox is off, or Krita was not restarted after enabling it.
- Document labels stay empty: click **Refresh**, or click the drawing once so it is the active document.
- Import says the size does not match: the PNG must be the same pixel size as the canvas. The plugin will not stretch or crop.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Plugin code lives in `ai_art_assistant/`. Krita discovers it through `ai_art_assistant.desktop`.

## License

MIT. See [LICENSE](LICENSE).
