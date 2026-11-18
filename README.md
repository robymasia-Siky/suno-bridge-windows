# Suno Bridge (Windows Edition) & Ableton Live AI Agent (MCP Server)

Porting completo per **Windows** di **Suno Bridge** (`suno-link` v0.7.33) e **Server MCP Autonomo (Model Context Protocol)** per consentire ad agenti AI (come Antigravity, Cursor, Claude Desktop) di agire come produttori musicali: autenticandosi sul tuo profilo Suno, generando tracce e inserendole in tempo reale dentro **Ableton Live**.

---

## 📑 Indice

1. [Panoramica dell'Architettura](#-panoramica-dellarchitettura)
2. [Installazione del Remote Script in Ableton Live](#-installazione-del-remote-script-in-ableton-live)
3. [Uso dell'Applicazione Desktop Suno Bridge su Windows](#-uso-dellapplicazione-desktop-suno-bridge-su-windows)
4. [Come Funziona la Creazione Tracce con Suno](#-come-funziona-la-creazione-tracce-con-suno)
5. [Server MCP: L'Agente AI Autonomo (Suno + Ableton)](#-server-mcp-lagente-ai-autonomo-suno--ableton)
6. [Come Ottenere il Token del Profilo Suno](#-come-ottenere-il-token-del-profilo-suno)
7. [Elenco dei Tool MCP per l'Agente](#-elenco-dei-tool-mcp-per-lagente)
8. [Esempi di Utilizzo con l'Agente](#-esempi-di-utilizzo-con-lagente)

---

## 🏗️ Panoramica dell'Architettura

Suno Bridge collega il cloud di Suno Studio con Ableton Live mediante un'architettura ibrida:

```
┌────────────────────────────────────────────────────────┐
│                      Suno Studio                       │
│                   (suno.com / Cloud)                   │
└───────────────────────▲────────┬───────────────────────┘
                        │ HTTPS  │ REST API
                        │ OAuth  │ Generazione Stems
┌───────────────────────┴────────▼───────────────────────┐
│              Suno Bridge (App Windows)                 │
│                 o Agente AI (MCP)                      │
│  - Gestione Token & Crediti Suno                       │
│  - Client OSC UDP (TX: 11000 / RX: 11001)              │
│  - Download Stems in Ableton Sample Library            │
└───────────────────────▲────────┬───────────────────────┘
                 OSC    │        │ OSC
             Port 11001 │        │ Port 11000
┌───────────────────────┴────────▼───────────────────────┐
│                     Ableton Live                       │
│          (Remote Script: Suno_Bridge in Python)        │
│  - Live Object Model (LOM) Control Surface             │
│  - Creazione Automatica Tracce Audio & MIDI            │
│  - Inserimento Clip all'interno del Loop corrente      │
└────────────────────────────────────────────────────────┘
```

---

## 🎛️ Installazione del Remote Script in Ableton Live

Il Remote Script Python permette la comunicazione bidirezionale tra Suno e Ableton Live (compatibile con **Ableton Live 11 e Live 12**).

1. Copia la cartella `unpacked_asar/suno-control` nella tua cartella utente di Ableton:
   ```
   C:\Users\<TuoUtente>\Documents\Ableton\User Library\Remote Scripts\Suno_Bridge
   ```
2. Apri **Ableton Live**.
3. Vai su **Opzioni → Preferenze → Link, Tempo & MIDI** (oppure premi `Ctrl + ,`).
4. Nella colonna **Superficie di Controllo** (*Control Surface*), seleziona dal menu a tendina: **`Suno_Bridge`**.
5. Nella barra di stato inferiore di Ableton comparirà il messaggio di conferma:  
   *`"Suno Bridge: Listening for OSC on port 11000"`*.

---

## 💻 Uso dell'Applicazione Desktop Suno Bridge su Windows

Nella cartella `unpacked_asar/dist/` trovi gli eseguibili pronti all'uso:
* **Installer Windows**: `Suno Bridge Setup 0.7.33.exe` (NSIS Installer)
* **Versione Portatile**: `Suno Bridge 0.7.33.exe` (Standalone, non richiede installazione)

### Avvio da riga di comando (Dev mode):
```bash
cd unpacked_asar
npx electron .
```

### Ricompilazione dell'installer:
```bash
cd unpacked_asar
npx electron-builder build --win --x64
```

---

## 🎵 Come Funziona la Creazione Tracce con Suno

Il flusso di lavoro segue 4 passaggi principali:

1. **Imposta il Loop in Ableton Live**:  
   Seleziona le battute desiderate nella timeline e premi `Ctrl + L`. Suno Bridge rileva in tempo reale BPM, battute e battuta iniziale.
2. **Crea la Parte in Suno Bridge**:  
   - Scegli lo strumento (Drums, Bass, Guitar, Piano, Vocals, Synth).
   - Inserisci stile e prompt sonoro (es: *"deep funky slap bass, analog warmth"*).
   - Premi **Create**.
3. **Ascolta i Take Generati**:  
   Suno genera le opzioni musicali in sincronia con il tempo del tuo progetto.
4. **Inserisci nel Progetto**:  
   Premi **Insert** sul take preferito: Suno Bridge scarica il file audio in alta qualità e ordina ad Ableton di creare la traccia audio e piazzare la clip esattamente sul loop!

---

## 🤖 Server MCP: L'Agente AI Autonomo (Suno + Ableton)

Il server MCP situato in `suno_ableton_mcp/server.py` consente a qualsiasi agente AI di comportarsi come **produttore musicale autonomo**. L'agente può:
* Leggere lo stato del tuo progetto Ableton (tempo, metronomo, tracce presenti).
* Connettersi al tuo account Suno e spendere i tuoi crediti per generare parti musicali.
* Scaricare automaticamente i file generati e inserirli dentro Ableton Live.
* Comporre e scrivere note MIDI direttamente dentro le clip.

### Configurazione dell'MCP Server

Aggiungi la configurazione al tuo client MCP preferito:

#### Per Cursor (`.cursor/mcp.json`):
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

#### Per Claude Desktop (`claude_desktop_config.json`):
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

## 🔑 Come Ottenere il Token del Profilo Suno

Per consentire all'agente di creare tracce usando il tuo account Suno e i tuoi crediti:

1. Apri il browser su [suno.com](https://suno.com) ed effettua l'accesso con il tuo account.
2. Premi `F12` (o tasto destro → *Ispeziona*) per aprire i **DevTools**.
3. Clicca sulla scheda **Network** (Rete).
4. Ricarica la pagina o fai un click su *Create*.
5. Seleziona una richiesta qualsiasi verso `studio-api.suno.com` (o `api.suno.com`).
6. Nella sezione **Headers → Request Headers**, trova la voce:
   ```http
   Authorization: Bearer <TUO_TOKEN_JWT>
   ```
7. Copia la stringa dopo `Bearer ` e forniscila al tuo agente AI dicendo:
   > *"Ecco il mio token Suno: eyJhbGciOi..."*
8. L'agente salverà automaticamente il token in locale in `~/.suno/credentials.json`. Da quel momento non dovrai più reinserirlo.

---

## 🛠️ Elenco dei Tool MCP per l'Agente

### Tool Suno Cloud:
| Tool | Descrizione |
| :--- | :--- |
| `suno_set_token` | Configura e memorizza il token di autenticazione Suno |
| `suno_get_user_info` | Restituisce il saldo crediti residuo, il piano attivo (Free, Pro, Premier) e l'username |
| `suno_generate_stem` | Invia una richiesta di generazione traccia audio su Suno Cloud |
| `suno_get_clip_status` | Verifica lo stato di rendering e restituisce l'URL del file audio |
| `suno_insert_take_to_ableton` | Scarica il file audio e comanda ad Ableton di creare la traccia e inserire la clip |

### Tool Ableton Live DAW:
| Tool | Descrizione |
| :--- | :--- |
| `ableton_get_song_info` | Legge BPM, tempo in quarti, stato riproduzione, numero di tracce e scene |
| `ableton_list_tracks` | Elenca tutte le tracce presenti nel progetto Live con i relativi nomi |
| `ableton_create_midi_track` | Crea una nuova traccia MIDI in Ableton |
| `ableton_create_audio_track` | Crea una nuova traccia Audio in Ableton |
| `ableton_insert_midi_notes` | Scrive note musicali direttamente dentro una clip (pitch 0-127, start, duration, velocity) |
| `ableton_transport` | Avvia (`start`), ferma (`stop`), mette in loop o modifica i BPM |

---

## 💡 Esempi di Utilizzo con l'Agente

Una volta configurato l'MCP, puoi interagire con l'agente con prompt in linguaggio naturale:

* **Generazione Audio con Suno**:
  > *"Controlla il tempo del mio progetto su Ableton. Poi genera con il mio account Suno una linea di basso funk a quel tempo e inseriscila nel progetto."*
* **Composizione MIDI**:
  > *"Crea una traccia MIDI chiamata 'Chords' e inserisci una progressione di accordi ii-V-I in Do Maggiore."*
* **Controllo DAW**:
  > *"Imposta il tempo del progetto a 124 BPM e avvia la riproduzione."*

---

## 📜 Licenza e Note Legali

Questo progetto è un porting e reverse engineering a scopo di ricerca e interoperabilità su Windows.  
Marchi e codice originale appartengono a **Suno, Inc.**  
L'integrazione DAW è basata su **Ableton Live Object Model (LOM)** e **python-osc**.
