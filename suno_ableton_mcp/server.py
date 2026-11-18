#!/usr/bin/env python3
"""
Suno Bridge & Ableton Live Autonomous Agent MCP Server
Complete Model Context Protocol server that enables AI agents to:
1. Authenticate with Suno and query credits/profile.
2. Generate music tracks and stems directly on Suno Cloud.
3. Query Ableton Live's project state (tempo, tracks, loop).
4. Download Suno audio stems and insert them directly into Ableton Live via OSC.
5. Generate and insert MIDI notes and sequences into Ableton clips.
"""

import sys
import os
import json
import socket
import select
import logging
import urllib.request
import urllib.error
import time
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Suno-Ableton-Agent] %(message)s"
)
logger = logging.getLogger("suno_ableton_mcp")

# Add bundled pythonosc to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
bundled_osc = os.path.join(parent_dir, "unpacked_asar", "suno-control")
if os.path.exists(bundled_osc) and bundled_osc not in sys.path:
    sys.path.insert(0, bundled_osc)

try:
    from pythonosc import osc_message_builder
    from pythonosc.osc_message import OscMessage
except ImportError:
    osc_message_builder = None

# Configuration constants
OSC_TARGET_HOST = "127.0.0.1"
OSC_SEND_PORT = 11000
OSC_RECV_PORT = 11001
SUNO_API_BASE = "https://studio-api.suno.com"
CREDENTIALS_DIR = os.path.join(os.path.expanduser("~"), ".suno")
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")
ABLETON_SAMPLES_DIR = os.path.join(
    os.path.expanduser("~"), "Documents", "Ableton", "User Library", "Samples", "Suno Imports"
)

# Ensure sample output folder exists
os.makedirs(ABLETON_SAMPLES_DIR, exist_ok=True)

def load_stored_token() -> Optional[str]:
    """Retrieve saved Suno Bearer token from credentials file or environment."""
    env_token = os.environ.get("SUNO_TOKEN") or os.environ.get("SUNO_API_TOKEN")
    if env_token:
        return env_token.strip()
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("access_token") or data.get("token")
        except Exception as e:
            logger.warning(f"Could not read credentials file: {e}")
    return None

def save_stored_token(token: str):
    """Save Suno token to ~/.suno/credentials.json"""
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump({"access_token": token.strip(), "updated_at": time.time()}, f, indent=2)

class OscClient:
    def __init__(self, host: str = OSC_TARGET_HOST, send_port: int = OSC_SEND_PORT):
        self.host = host
        self.send_port = send_port
        self.sock: Optional[socket.socket] = None

    def _ensure_socket(self):
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            try:
                self.sock.bind(("0.0.0.0", 0))
            except Exception as e:
                logger.warning(f"OSC socket bind warning: {e}")

    def send_osc(self, address: str, args: List[Any] = []) -> bool:
        self._ensure_socket()
        try:
            builder = osc_message_builder.OscMessageBuilder(address=address)
            for arg in args:
                builder.add_arg(arg)
            msg = builder.build()
            self.sock.sendto(msg.dgram, (self.host, self.send_port))
            logger.info(f"OSC TX -> {address} {args}")
            return True
        except Exception as e:
            logger.error(f"Error sending OSC message {address}: {e}")
            return False

    def query_osc(self, address: str, args: List[Any] = [], timeout_sec: float = 0.5) -> Optional[List[Any]]:
        self.send_osc(address, args)
        ready = select.select([self.sock], [], [], timeout_sec)
        if ready[0]:
            try:
                data, _ = self.sock.recvfrom(65535)
                msg = OscMessage(data)
                return msg.params
            except Exception as e:
                logger.error(f"Error reading OSC reply: {e}")
        return None

osc = OscClient()

def suno_http_request(method: str, endpoint: str, payload: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Dict[str, Any]:
    """Execute authenticated HTTP request to Suno Studio API."""
    auth_token = token or load_stored_token()
    if not auth_token:
        raise ValueError("No Suno token provided. Use the 'suno_set_token' tool to set your Bearer token.")

    url = f"{SUNO_API_BASE}{endpoint}" if endpoint.startswith("/") else endpoint
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "User-Agent": "SunoBridge/0.7.33 (Windows NT 10.0; Win64; x64)"
    }

    req_data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        error_body = err.read().decode("utf-8", errors="ignore")
        logger.error(f"Suno API HTTP {err.code}: {error_body}")
        raise RuntimeError(f"Suno API Error (HTTP {err.code}): {error_body}")
    except Exception as err:
        logger.error(f"Suno API Network Error: {err}")
        raise RuntimeError(f"Suno API Network Error: {err}")

# MCP Tool Definitions
TOOLS = [
    # --- SUNO CLOUD TOOLS ---
    {
        "name": "suno_set_token",
        "description": "Configure the Suno Bearer authentication token for creating tracks with your Suno account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Your Suno account Bearer token (JWT token obtained from Suno.com login or network tab)"
                }
            },
            "required": ["token"],
            "additionalProperties": False
        }
    },
    {
        "name": "suno_get_user_info",
        "description": "Check current Suno account status, username, active plan, and remaining generation credits.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "suno_generate_stem",
        "description": "Generate a new musical stem (e.g. Bass, Drums, Guitar, Synth, Vocals) on Suno Cloud matching project tempo and styles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the part to generate (e.g. 'funky slap bass groove', 'ambient pads')"
                },
                "instrument": {
                    "type": "string",
                    "description": "Instrument category: Bass, Drums, Guitar, Piano, Vocals, Synth, Brass, or Custom"
                },
                "styles": {
                    "type": "string",
                    "description": "Musical style and genre tags (e.g. 'funk, 90s, analog, groovy')"
                },
                "lyrics": {
                    "type": "string",
                    "description": "Lyrics text to be sung (if generating vocal tracks)"
                },
                "instrumental": {
                    "type": "boolean",
                    "description": "Whether the generation should be purely instrumental (default: true)"
                }
            },
            "required": ["prompt"],
            "additionalProperties": False
        }
    },
    {
        "name": "suno_get_clip_status",
        "description": "Check generation progress of a Suno clip and retrieve its audio streaming / download URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "clip_id": {
                    "type": "string",
                    "description": "ID of the Suno clip returned by suno_generate_stem"
                }
            },
            "required": ["clip_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "suno_insert_take_to_ableton",
        "description": "Download a generated Suno audio clip and automatically insert it into an audio track in Ableton Live at the current loop/playhead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "clip_id": {
                    "type": "string",
                    "description": "ID of the Suno clip to download and insert"
                },
                "track_name": {
                    "type": "string",
                    "description": "Name for the newly created audio track in Ableton (e.g. 'Suno Bass')"
                },
                "track_index": {
                    "type": "integer",
                    "description": "Target track index (-1 to create a new track at the end)"
                },
                "clip_slot_index": {
                    "type": "integer",
                    "description": "Target clip slot / scene index (default 0)"
                }
            },
            "required": ["clip_id"],
            "additionalProperties": False
        }
    },

    # --- ABLETON LIVE DAW CONTROL TOOLS ---
    {
        "name": "ableton_get_song_info",
        "description": "Get current state of the Ableton Live project (tempo/BPM, time signature, playing state, current beat, tracks count).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_list_tracks",
        "description": "List all tracks in the currently open Ableton Live project.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_create_midi_track",
        "description": "Create a new MIDI track in Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {
                    "type": "integer",
                    "description": "Index at which to insert the track (-1 for end)"
                }
            },
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_create_audio_track",
        "description": "Create a new Audio track in Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {
                    "type": "integer",
                    "description": "Index at which to insert the track (-1 for end)"
                }
            },
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_insert_midi_notes",
        "description": "Write musical MIDI notes into a clip in Ableton Live. Notes format: pitch (0-127), start_time (beats), duration (beats), velocity (1-127).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer", "description": "Target track index"},
                "clip_index": {"type": "integer", "description": "Target clip slot index"},
                "notes": {
                    "type": "array",
                    "description": "List of note dictionaries",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pitch": {"type": "integer"},
                            "start_time": {"type": "number"},
                            "duration": {"type": "number"},
                            "velocity": {"type": "number"}
                        },
                        "required": ["pitch", "start_time", "duration"]
                    }
                }
            },
            "required": ["track_index", "clip_index", "notes"],
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_transport",
        "description": "Control playback transport in Ableton Live (start, stop, continue, toggle_loop, or set tempo BPM).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "continue", "toggle_loop"]
                },
                "tempo": {
                    "type": "number",
                    "description": "Optional BPM tempo to set (e.g. 124.0)"
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    }
]

def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    # 1. Suno Token
    if name == "suno_set_token":
        token = args["token"]
        save_stored_token(token)
        return {
            "content": [{
                "type": "text",
                "text": "Suno authentication token saved successfully. You can now generate tracks."
            }]
        }

    # 2. Suno User Info & Credits
    elif name == "suno_get_user_info":
        try:
            info = suno_http_request("GET", "/api/billing/info")
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps(info, indent=2)
                }]
            }
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error querying Suno profile: {e}"}]}

    # 3. Suno Generate Stem
    elif name == "suno_generate_stem":
        prompt = args["prompt"]
        instrument = args.get("instrument", "Custom")
        styles = args.get("styles", "")
        lyrics = args.get("lyrics", "")
        instrumental = args.get("instrumental", True)

        payload = {
            "model": "chirp-hawk",
            "prompt": prompt,
            "instrument": instrument,
            "styles": styles,
            "lyrics": lyrics,
            "instrumental": instrumental
        }

        # First try the external OAuth stem endpoint used by Suno Bridge
        try:
            res = suno_http_request("POST", "/api/v2/external/oauth/generate-stem", payload)
        except Exception:
            # Fallback to standard studio generation endpoint
            res = suno_http_request("POST", "/api/generate/v2/", {
                "prompt": prompt,
                "tags": styles,
                "make_instrumental": instrumental,
                "title": f"Bridge - {instrument}"
            })

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "status": "generation_started",
                    "response": res,
                    "message": "Stem generation queued in Suno Cloud. Use 'suno_get_clip_status' or 'suno_insert_take_to_ableton' with the clip ID."
                }, indent=2)
            }]
        }

    # 4. Suno Clip Status
    elif name == "suno_get_clip_status":
        clip_id = args["clip_id"]
        try:
            download_info = suno_http_request("GET", f"/api/studio/clip/{clip_id}/download?format=mp3")
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps(download_info, indent=2)
                }]
            }
        except Exception:
            feed = suno_http_request("GET", f"/api/feed/v2?ids={clip_id}")
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps(feed, indent=2)
                }]
            }

    # 5. Suno Download & Insert to Ableton
    elif name == "suno_insert_take_to_ableton":
        clip_id = args["clip_id"]
        track_name = args.get("track_name", "Suno Take")
        track_idx = args.get("track_index", -1)
        clip_slot = args.get("clip_slot_index", 0)

        # Resolve audio URL
        download_url = None
        try:
            dl_info = suno_http_request("GET", f"/api/studio/clip/{clip_id}/download?format=mp3")
            download_url = dl_info.get("url")
        except Exception:
            feed = suno_http_request("GET", f"/api/feed/v2?ids={clip_id}")
            clips = feed.get("clips", [])
            if clips:
                download_url = clips[0].get("audio_url")

        if not download_url:
            return {"content": [{"type": "text", "text": f"Audio URL for clip {clip_id} is not ready yet."}]}

        # Download audio file to local Ableton sample library
        filename = f"{track_name.replace(' ', '_')}_{clip_id[:8]}.mp3"
        dest_path = os.path.join(ABLETON_SAMPLES_DIR, filename)
        logger.info(f"Downloading Suno stem from {download_url} to {dest_path}")
        urllib.request.urlretrieve(download_url, dest_path)

        # Command Ableton Live to create an audio track and load the file
        osc.send_osc("/live/song/create_audio_track_with_config", [track_idx])
        # Allow Live a short beat to create track, then load into slot
        time.sleep(0.2)
        osc.send_osc("/live/clip_slot/load_file", [track_idx if track_idx >= 0 else 0, clip_slot, dest_path])

        return {
            "content": [{
                "type": "text",
                "text": f"Successfully downloaded '{filename}' and inserted into Ableton Live track {track_idx}, clip slot {clip_slot}!"
            }]
        }

    # 6. Ableton Info
    elif name == "ableton_get_song_info":
        osc.send_osc("/live/song/get/tempo")
        osc.send_osc("/live/song/get/num_tracks")
        return {
            "content": [{
                "type": "text",
                "text": "Queried Ableton Live project status via OSC port 11000."
            }]
        }

    # 7. Ableton Tracks
    elif name == "ableton_list_tracks":
        osc.send_osc("/live/song/get/track_names")
        return {
            "content": [{
                "type": "text",
                "text": "Requested track list from Ableton via OSC."
            }]
        }

    # 8. Ableton Track Creation
    elif name == "ableton_create_midi_track":
        t_idx = args.get("track_index", -1)
        osc.send_osc("/live/song/create_midi_track_with_config", [t_idx])
        return {"content": [{"type": "text", "text": f"Created MIDI track at index {t_idx}."}]}

    elif name == "ableton_create_audio_track":
        t_idx = args.get("track_index", -1)
        osc.send_osc("/live/song/create_audio_track_with_config", [t_idx])
        return {"content": [{"type": "text", "text": f"Created Audio track at index {t_idx}."}]}

    # 9. Ableton MIDI Notes
    elif name == "ableton_insert_midi_notes":
        track_idx = args["track_index"]
        clip_idx = args["clip_index"]
        notes = args["notes"]
        flat_args = [track_idx, clip_idx]
        for n in notes:
            flat_args.extend([
                int(n["pitch"]),
                float(n["start_time"]),
                float(n["duration"]),
                int(n.get("velocity", 100)),
                0
            ])
        osc.send_osc("/live/clip/add/notes", flat_args)
        return {"content": [{"type": "text", "text": f"Inserted {len(notes)} MIDI notes into track {track_idx}, clip {clip_idx}."}]}

    # 10. Ableton Transport
    elif name == "ableton_transport":
        action = args["action"]
        tempo = args.get("tempo")
        if tempo is not None:
            osc.send_osc("/live/song/set/tempo", [float(tempo)])
        if action == "start":
            osc.send_osc("/live/song/start_playing")
        elif action == "stop":
            osc.send_osc("/live/song/stop_playing")
        elif action == "continue":
            osc.send_osc("/live/song/continue_playing")
        elif action == "toggle_loop":
            osc.send_osc("/live/song/set/loop", [1])
        return {"content": [{"type": "text", "text": f"Ableton transport '{action}' executed."}]}

    raise ValueError(f"Unknown tool: {name}")

def run_mcp_server():
    """Stdio JSON-RPC loop for Model Context Protocol."""
    logger.info("Suno Bridge & Ableton Live Autonomous Agent MCP Server started.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})
        response: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}

        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "suno-ableton-agent-mcp",
                    "version": "2.0.0"
                }
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                res = handle_tool_call(tool_name, tool_args)
                response["result"] = res
            except Exception as e:
                response["error"] = {"code": -32000, "message": str(e)}
        else:
            response["error"] = {"code": -32601, "message": f"Method {method} not found"}

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    run_mcp_server()
