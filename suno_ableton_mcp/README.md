# Suno & Ableton Live Autonomous Agent MCP Server (v2.0)

Un server MCP (Model Context Protocol) completo che trasforma qualsiasi agente AI (Antigravity, Cursor, Claude Desktop) in un **produttore musicale autonomo**, in grado sia di controllare **Ableton Live** sia di accedere al tuo account **Suno** per generare e inserire tracce.

---

## 🛠️ Tool Disponibili per l'Agente AI

### 1. Gestione Account Suno
* **`suno_set_token`**: Salva il tuo Bearer Token di Suno (`~/.suno/credentials.json`) per consentire all'agente di operare con il tuo account e i tuoi crediti.
* **`suno_get_user_info`**: Legge il saldo crediti, il piano attivo e i dati dell'account.

### 2. Generazione Tracce Suno
* **`suno_generate_stem`**: Chiama l'API di Suno Cloud per generare parti musicali (Basso, Batteria, Chitarra, Voce, Synth) con prompt e stili specificati.
* **`suno_get_clip_status`**: Monitora lo stato di rendering e restituisce l'URL audio del take.
* **`suno_insert_take_to_ableton`**: **Fa tutto in automatico**: scarica il file audio in alta qualità in `User Library/Samples/Suno Imports` e comanda Ableton Live via OSC per creare la traccia e piazzare la clip al loop corrente!

### 3. Controllo DAW Ableton Live
* **`ableton_get_song_info`**: Legge tempo (BPM), battuta corrente, tracce presenti.
* **`ableton_list_tracks`**: Elenca tutte le tracce del progetto Live.
* **`ableton_create_midi_track`** / **`ableton_create_audio_track`**: Crea tracce al volo.
* **`ableton_insert_midi_notes`**: Compone e scrive sequenze MIDI (note, accordi, ritmi) dentro le clip di Ableton.
* **`ableton_transport`**: Avvia/ferma la riproduzione o imposta i BPM.

---

## ⚙️ Configurazione

### In Cursor (`.cursor/mcp.json`) o Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "suno-ableton": {
      "command": "python",
      "args": [
        "C:\\Users\\Utente\\Desktop\\suno bridge\\suno_ableton_mcp\\server.py"
      ]
    }
  }
}
```

---

## 🔑 Come recuperare il Token del tuo Account Suno

1. Vai su [suno.com](https://suno.com) e accedi con il tuo account.
2. Premi `F12` per aprire i DevTools del browser.
3. Vai nella scheda **Network** (Rete), ricarica la pagina o clicca su una sezione.
4. Clicca su una chiamata qualsiasi verso `studio-api.suno.com` o `api.suno.com`.
5. Nei **Request Headers**, copia il valore dopo `Authorization: Bearer <TOKEN>`.
6. Dillo al tuo agente:
   > *"Ecco il mio token Suno: eyJhbGciOi..."*  
   L'agente userà il tool `suno_set_token` e lo memorizzerà per tutte le sessioni future.
