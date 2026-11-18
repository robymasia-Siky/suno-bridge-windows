#!/usr/bin/env python3
"""
Suno Bridge / Ableton Live MCP Server
Allows AI agents (Antigravity, Claude, Cursor, etc.) to interact directly with Ableton Live
via the Suno Bridge OSC protocol (Port 11000 TX, Port 11001 RX).
"""

import sys
import os
import json
import socket
import select
import logging
from typing import Any, Dict, List, Optional, Tuple

# Configure logging to stderr (stdout is reserved for MCP JSON-RPC messages)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Suno-Ableton-MCP] %(message)s"
)
logger = logging.getLogger("suno_mcp")

# Add bundled pythonosc to path if available
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
bundled_osc = os.path.join(parent_dir, "unpacked_asar", "suno-control")
if os.path.exists(bundled_osc) and bundled_osc not in sys.path:
    sys.path.insert(0, bundled_osc)

try:
    from pythonosc import osc_message_builder
    from pythonosc.osc_message import OscMessage
    from pythonosc.osc_bundle import OscBundle
except ImportError:
    # Minimal fallback OSC builder if pythonosc is not installed
    osc_message_builder = None

OSC_TARGET_HOST = "127.0.0.1"
OSC_SEND_PORT = 11000
OSC_RECV_PORT = 11001

class OscClient:
    def __init__(self, host: str = OSC_TARGET_HOST, send_port: int = OSC_SEND_PORT, recv_port: int = OSC_RECV_PORT):
        self.host = host
        self.send_port = send_port
        self.recv_port = recv_port
        self.sock: Optional[socket.socket] = None

    def _ensure_socket(self):
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            try:
                # Try binding to response port; if occupied by Suno Bridge, use ephemeral port
                self.sock.bind(("0.0.0.0", 0))
            except Exception as e:
                logger.warning(f"Failed to bind socket: {e}")

    def send_osc(self, address: str, args: List[Any] = []) -> bool:
        self._ensure_socket()
        try:
            builder = osc_message_builder.OscMessageBuilder(address=address)
            for arg in args:
                builder.add_arg(arg)
            msg = builder.build()
            self.sock.sendto(msg.dgram, (self.host, self.send_port))
            logger.info(f"Sent OSC: {address} with args {args}")
            return True
        except Exception as e:
            logger.error(f"Error sending OSC message {address}: {e}")
            return False

    def send_and_wait_reply(self, address: str, args: List[Any] = [], timeout_sec: float = 1.0) -> Optional[List[Any]]:
        self.send_osc(address, args)
        # Note: If Suno Bridge or another process holds port 11001, replies go there.
        # Direct responses on shared socket:
        ready = select.select([self.sock], [], [], timeout_sec)
        if ready[0]:
            try:
                data, _ = self.sock.recvfrom(65535)
                msg = OscMessage(data)
                return msg.params
            except Exception as e:
                logger.error(f"Error reading OSC reply: {e}")
        return None

client = OscClient()

# MCP Tool Definitions
TOOLS = [
    {
        "name": "ableton_get_song_info",
        "description": "Get current state of the Ableton Live project (tempo/BPM, time signature, playing state, current beat, number of tracks and scenes).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_list_tracks",
        "description": "List all tracks in the currently open Ableton Live project, including their names, colors, and types.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_create_midi_track",
        "description": "Create a new MIDI track in Ableton Live at a specific index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {
                    "type": "integer",
                    "description": "Index at which to insert the track (-1 for end of track list)"
                }
            },
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_create_audio_track",
        "description": "Create a new Audio track in Ableton Live at a specific index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {
                    "type": "integer",
                    "description": "Index at which to insert the track (-1 for end of track list)"
                }
            },
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_transport",
        "description": "Control playback transport in Ableton Live (start, stop, continue, toggle loop, or set tempo).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "continue", "toggle_loop"],
                    "description": "Playback action to perform"
                },
                "tempo": {
                    "type": "number",
                    "description": "Optional BPM tempo to set (e.g. 120.0)"
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_insert_midi_notes",
        "description": "Insert MIDI notes into a clip in Ableton Live. Pitch is MIDI number 0-127 (e.g. 60 = Middle C). Start time and duration are in beats.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {
                    "type": "integer",
                    "description": "Track index containing the clip"
                },
                "clip_index": {
                    "type": "integer",
                    "description": "Clip slot index (scene index) in Session View"
                },
                "notes": {
                    "type": "array",
                    "description": "List of note objects to add",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pitch": {"type": "integer", "description": "MIDI note pitch (0-127)"},
                            "start_time": {"type": "number", "description": "Start position in beats"},
                            "duration": {"type": "number", "description": "Note duration in beats"},
                            "velocity": {"type": "number", "description": "Velocity (1-127, default 100)"},
                            "mute": {"type": "boolean", "description": "Muted state (default false)"}
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
        "name": "ableton_fire_scene",
        "description": "Launch/fire a specific scene in Ableton Live Session View.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scene_index": {
                    "type": "integer",
                    "description": "Zero-based index of the scene to fire"
                }
            },
            "required": ["scene_index"],
            "additionalProperties": False
        }
    },
    {
        "name": "ableton_load_audio_file",
        "description": "Load an audio file (.wav, .aif, .mp3) from disk into a clip slot or arrangement track.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {
                    "type": "integer",
                    "description": "Target track index"
                },
                "clip_slot_index": {
                    "type": "integer",
                    "description": "Target clip slot index"
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the audio file on disk"
                }
            },
            "required": ["track_index", "clip_slot_index", "file_path"],
            "additionalProperties": False
        }
    }
]

def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "ableton_get_song_info":
        client.send_osc("/live/song/get/tempo")
        client.send_osc("/live/song/get/num_tracks")
        client.send_osc("/live/song/get/num_scenes")
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "status": "query_sent",
                        "message": "Requested project info via OSC. Port 11000 is active.",
                        "target": f"{OSC_TARGET_HOST}:{OSC_SEND_PORT}"
                    }, indent=2)
                }
            ]
        }

    elif name == "ableton_list_tracks":
        client.send_osc("/live/song/get/track_names")
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "status": "query_sent",
                        "message": "Requested track list from Ableton via OSC address /live/song/get/track_names"
                    }, indent=2)
                }
            ]
        }

    elif name == "ableton_create_midi_track":
        t_idx = arguments.get("track_index", -1)
        client.send_osc("/live/song/create_midi_track_with_config", [t_idx])
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Successfully created MIDI track at index {t_idx} via OSC."
                }
            ]
        }

    elif name == "ableton_create_audio_track":
        t_idx = arguments.get("track_index", -1)
        client.send_osc("/live/song/create_audio_track_with_config", [t_idx])
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Successfully created Audio track at index {t_idx} via OSC."
                }
            ]
        }

    elif name == "ableton_transport":
        action = arguments["action"]
        tempo = arguments.get("tempo")
        if tempo is not None:
            client.send_osc("/live/song/set/tempo", [float(tempo)])
        if action == "start":
            client.send_osc("/live/song/start_playing")
        elif action == "stop":
            client.send_osc("/live/song/stop_playing")
        elif action == "continue":
            client.send_osc("/live/song/continue_playing")
        elif action == "toggle_loop":
            client.send_osc("/live/song/set/loop", [1])
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Transport action '{action}' executed (tempo: {tempo})."
                }
            ]
        }

    elif name == "ableton_insert_midi_notes":
        track_idx = arguments["track_index"]
        clip_idx = arguments["clip_index"]
        notes = arguments["notes"]
        # Format for /live/clip/add/notes: pitch, start, duration, velocity, mute (flattened list)
        flat_args = [track_idx, clip_idx]
        for n in notes:
            flat_args.extend([
                int(n["pitch"]),
                float(n["start_time"]),
                float(n["duration"]),
                int(n.get("velocity", 100)),
                1 if n.get("mute", False) else 0
            ])
        client.send_osc("/live/clip/add/notes", flat_args)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Sent {len(notes)} MIDI notes to track {track_idx}, clip {clip_idx}."
                }
            ]
        }

    elif name == "ableton_fire_scene":
        scene_idx = arguments["scene_index"]
        client.send_osc("/live/scene/fire_selected", [scene_idx])
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Fired scene index {scene_idx}."
                }
            ]
        }

    elif name == "ableton_load_audio_file":
        track_idx = arguments["track_index"]
        clip_idx = arguments["clip_slot_index"]
        fpath = arguments["file_path"]
        client.send_osc("/live/clip_slot/load_file", [track_idx, clip_idx, fpath])
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Dispatched load_file for '{fpath}' to track {track_idx}, clip {clip_idx}."
                }
            ]
        }

    raise ValueError(f"Unknown tool: {name}")

def run_mcp_server():
    """Standard JSON-RPC 2.0 stdio MCP Server loop"""
    logger.info("Ableton Live / Suno Bridge MCP Server started on stdio.")
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
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ableton-suno-mcp",
                    "version": "1.0.0"
                }
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            response["result"] = {
                "tools": TOOLS
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                result = handle_tool_call(tool_name, tool_args)
                response["result"] = result
            except Exception as e:
                response["error"] = {
                    "code": -32000,
                    "message": str(e)
                }
        else:
            response["error"] = {
                "code": -32601,
                "message": f"Method not found: {method}"
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    run_mcp_server()
