# Suno Bridge & Ableton Live MCP Server

Un server MCP (Model Context Protocol) standard stdio che permette ad agenti AI (come Antigravity, Cursor, Claude Desktop, ecc.) di controllare **Ableton Live** e comunicare con il protocollo **Suno Bridge**.

## Funzionalità (Tool per l'Agente AI)

1. **`ableton_get_song_info`**: Legge tempo (BPM), metronomo, beat attuale, numero di tracce e scene del progetto.
2. **`ableton_list_tracks`**: Elenca tutte le tracce presenti (Audio, MIDI, Return).
3. **`ableton_create_midi_track`**: Crea al volo una traccia MIDI.
4. **`ableton_create_audio_track`**: Crea al volo una traccia Audio.
5. **`ableton_insert_midi_notes`**: Inserisce note musicali (pitch, start_time, duration, velocity) direttamente in una clip di Ableton!
6. **`ableton_transport`**: Avvia/ferma la riproduzione o imposta i BPM (`start`, `stop`, `continue`, `toggle_loop`, `tempo`).
7. **`ableton_fire_scene`**: Lancia l'esecuzione di una scena della Session View.
8. **`ableton_load_audio_file`**: Carica un file audio/sample generato da disco in una clip o traccia.

## Configurazione

### 1. In Antigravity / Claude Desktop
Aggiungi nel tuo file di configurazione MCP (`claude_desktop_config.json` o configurazione MCP di Antigravity):

```json
{
  "mcpServers": {
    "ableton-suno": {
      "command": "python",
      "args": [
        "C:\\Users\\Utente\\Desktop\\suno bridge\\suno_ableton_mcp\\server.py"
      ]
    }
  }
}
```

### 2. In Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "ableton-suno": {
      "command": "python",
      "args": [
        "C:/Users/Utente/Desktop/suno bridge/suno_ableton_mcp/server.py"
      ]
    }
  }
}
```

## Prerequisiti
* Ableton Live aperto con la Superficie di Controllo **`Suno_Bridge`** selezionata in *Preferenze -> Link, Tempo & MIDI*.
