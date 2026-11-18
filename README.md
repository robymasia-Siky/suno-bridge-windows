# Suno Bridge (Windows Edition) & Ableton Live AI MCP Server

**Suno Bridge** porting for Windows + **Ableton Live AI MCP Server** (Model Context Protocol).

Originally distributed by Suno only for macOS, this repository provides:
1. **Windows Port of Suno Bridge** (`suno-link` v0.7.33):
   - Patched Electron backend for native Windows process management (`tasklist`, `taskkill`, Windows path resolution).
   - Electron-builder packaging configuration for Windows (`.exe` NSIS installer & portable executable).
   - Seamless bidirectional OSC communication with Ableton Live on Windows.
2. **Ableton Live Remote Script** (`Suno_Bridge`):
   - Python 3 MIDI Remote Script for Ableton Live 11 & 12.
   - Listens on OSC port `11000` (TX) and sends replies on `11001` (RX).
3. **Ableton Live MCP Server**:
   - Standard Model Context Protocol (MCP) server for AI Agents (Antigravity, Cursor, Claude Desktop, etc.).
   - Enables AI agents to read Ableton project state, create audio/MIDI tracks, insert generated MIDI notes, and trigger scenes.

---

## Architecture

```
┌───────────────────────────────────────────────┐
│              Suno Studio Cloud                │
└───────────────────────▲───────────────────────┘
                        │ HTTPS
┌───────────────────────▼───────────────────────┐
│          Suno Bridge (Windows App)            │
│  - Electron + Node.js (Patched for Win32)     │
│  - Project Scanner & .als Converter           │
│  - DPAPI Secure Credential Storage            │
└───────────────────────▲───────────────────────┘
                 OSC    │ UDP 11000 / 11001
┌───────────────────────▼───────────────────────┐
│                 Ableton Live                  │
│       (Remote Script: Suno_Bridge)            │
│  - Python 3 LOM (Live Object Model)           │
│  - Track & Clip Arrangement Control           │
└───────────────────────▲───────────────────────┘
                 OSC    │ UDP 11000 / 11001
┌───────────────────────▼───────────────────────┐
│            Ableton Live MCP Server            │
│          (For AI Coding Agents)               │
└───────────────────────────────────────────────┘
```

---

## Quick Start: Ableton Live Remote Script Installation

1. Copy the `unpacked_asar/suno-control` folder to your Ableton User Library:
   ```
   C:\Users\<YourUser>\Documents\Ableton\User Library\Remote Scripts\Suno_Bridge
   ```
2. Open **Ableton Live**.
3. Open **Preferences** (`Ctrl + ,`) -> **Link, Tempo & MIDI**.
4. In the **Control Surface** list, choose **`Suno_Bridge`**.
5. Live's status bar will confirm:
   `Suno Bridge: Listening for OSC on port 11000`

---

## Running / Building Suno Bridge for Windows

The source and build assets are in `unpacked_asar/`:

* **Start in Development Mode**:
  ```bash
  cd unpacked_asar
  npx electron .
  ```
* **Build Windows Installer & Portable Executable**:
  ```bash
  cd unpacked_asar
  npx electron-builder build --win --x64
  ```
  Artifacts will be generated in `unpacked_asar/dist/`:
  - `Suno Bridge Setup 0.7.33.exe` (NSIS Installer)
  - `Suno Bridge 0.7.33.exe` (Portable)

---

## Ableton Live MCP Server for AI Agents

Located in `suno_ableton_mcp/`.

### Configuration in Claude Desktop / Antigravity / Cursor

```json
{
  "mcpServers": {
    "ableton-suno": {
      "command": "python",
      "args": [
        "C:\\path\\to\\suno_ableton_mcp\\server.py"
      ]
    }
  }
}
```

### Available MCP Tools

* `ableton_get_song_info`: Read current tempo, signature, playing state, beat.
* `ableton_list_tracks`: List all audio/MIDI tracks.
* `ableton_create_midi_track`: Create a new MIDI track.
* `ableton_create_audio_track`: Create a new Audio track.
* `ableton_insert_midi_notes`: Add notes directly into clips (pitch, start beat, duration, velocity).
* `ableton_transport`: Control playback (start, stop, continue, tempo).
* `ableton_fire_scene`: Trigger scenes.
* `ableton_load_audio_file`: Load samples/stems into clip slots.

---

## License & Credits

Reverse-engineered and adapted for Windows research and interoperability.
Original Suno Bridge code & trademarks belong to Suno, Inc.
Remote Script based on Ableton Live Object Model (LOM) and python-osc.
