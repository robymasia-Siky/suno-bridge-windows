from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import tempfile
from functools import partial
from typing import Any, List, Optional, Tuple
from uuid import UUID

import Live

from .handler import AbletonOSCHandler

CAPTURE_VERSION: int = 2
CAPTURE_MAX_BYTES: int = 16 * 1024 * 1024
CAPTURE_MAX_CLIPS: int = 10000
CAPTURE_MAX_NOTES: int = 100000
CAPTURE_MAX_WARP_MARKERS: int = 10000


def get_capture_number(value: Any) -> float:
    """Reject unavailable or non-finite native musical values."""
    number: float = float(value)
    if not math.isfinite(number):
        raise ValueError("Live returned an invalid musical value; retry capture")
    return number


def get_amplitude_from_decibels(display: str) -> float:
    """Translate Live's displayed gain instead of its nonlinear control value."""
    text: str = display.strip().replace(",", ".").lower()
    if text in ("-inf db", "-∞ db"):
        return 0.0
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*db", text):
        raise ValueError(
            "Live gain could not be read. Render the track to audio, then retry."
        )
    decibels: float = get_capture_number(text[:-2].strip())
    return 10.0 ** (decibels / 20.0)


def get_mixer_amplitude(parameter: Any) -> float:
    """Read the mixer fader's audible gain from its native display value."""
    return get_amplitude_from_decibels(parameter.str_for_value(parameter.value))


def get_current_clips_snapshot(
    song: Any, capture_id: str, set_id: str, start: float, end: float
) -> dict[str, Any]:
    """Read materialized arrangement clips without changing Live or its history."""
    reasons: list[str] = []
    if song.record_mode or song.session_record:
        reasons.append("Stop recording, then retry current-clips capture.")
    if song.back_to_arranger:
        reasons.append(
            "Session playback overrides the arrangement. Return to Arrangement, then retry."
        )
    tracks: list[dict[str, Any]] = []
    clip_count: int = 0
    note_count: int = 0
    marker_count: int = 0
    if len(song.tracks) > 1000:
        raise ValueError("Too many tracks for current-clips capture")
    inventory: dict[str, int] = {
        "arrangementClips": 0,
        "outsideRange": 0,
        "trackMuted": 0,
        "clipMuted": 0,
        "audioCandidates": 0,
    }
    soloed_return_indices: frozenset[int] = frozenset(
        index
        for index, return_track in enumerate(song.return_tracks)
        if return_track.solo and not return_track.mute
    )
    unmuted_return_indices: frozenset[int] = frozenset(
        index
        for index, return_track in enumerate(song.return_tracks)
        if not return_track.mute
    )
    for track_index, track in enumerate(song.tracks):
        clips: list[dict[str, Any]] = []
        mixer: Any = track.mixer_device
        output_tracks: list[Any] = [track]
        while (
            output_tracks[-1].is_grouped
            and output_tracks[-1].output_routing_type.display_name == "Group"
        ):
            parent: Any = output_tracks[-1].group_track
            if parent is None or parent in output_tracks:
                raise ValueError("Live returned invalid Group routing; retry capture")
            output_tracks.append(parent)
        output_muted: bool = False
        output_volume: float = 1.0
        return_volume: Optional[float] = None
        return_output_count: int = len(output_tracks)
        for output_index, output_track in enumerate(output_tracks):
            output_muted = output_muted or output_track.mute
            output_volume *= get_mixer_amplitude(output_track.mixer_device.volume)
            # A send leaves the Group chain before downstream mixer suppression.
            if (
                return_volume is None
                and not output_muted
                and any(
                    get_capture_number(send.value) > 0
                    for send_index, send in enumerate(output_track.mixer_device.sends)
                    if send_index in unmuted_return_indices
                )
            ):
                return_volume = output_volume
                return_output_count = output_index + 1
        # Conditioning ignores playback solo and arm state.
        if (output_muted or output_volume == 0) and return_volume is not None:
            audible: bool = True
            volume: float = return_volume
            captured_output_count: int = return_output_count
        else:
            audible = not output_muted
            volume = output_volume
            captured_output_count = len(output_tracks)
        sends_to_soloed_return: bool = audible and any(
            get_capture_number(send.value) > 0
            for output_track in output_tracks[:captured_output_count]
            for send_index, send in enumerate(output_track.mixer_device.sends)
            if send_index in soloed_return_indices
        )
        for clip_index, clip in enumerate(
            () if track.is_foldable else track.arrangement_clips
        ):
            inventory["arrangementClips"] += 1
            clip_start: float = get_capture_number(clip.start_time)
            clip_end: float = get_capture_number(clip.end_time)
            if clip_end <= start or clip_start >= end:
                inventory["outsideRange"] += 1
                continue
            if audible and not clip.muted and sends_to_soloed_return:
                reasons.append(
                    f"{track.name} sends to a soloed return. Render the audible return mix to audio in Live, mute the contributing sources and returns, clear solos, then retry."
                )
            if not audible or clip.muted:
                inventory["trackMuted" if not audible else "clipMuted"] += 1
                continue
            clip_count += 1
            if clip_count > CAPTURE_MAX_CLIPS:
                raise ValueError("Too many arrangement clips for current-clips capture")
            clip_data: dict[str, Any] = {
                "index": clip_index,
                "name": clip.name,
                "start": clip_start,
                "end": clip_end,
                "startMarker": get_capture_number(clip.start_marker),
                "loopStart": get_capture_number(clip.loop_start),
                "loopEnd": get_capture_number(clip.loop_end),
                "looping": bool(clip.looping),
                "muted": bool(clip.muted),
                "audio": bool(clip.is_audio_clip),
            }
            if clip.is_recording:
                reasons.append(f"Stop recording the clip {clip.name}, then retry.")
            if audible and not clip.muted and clip.has_envelopes:
                reasons.append(
                    f"{clip.name} has clip automation. Render it to audio in Live first."
                )
            if audible and not clip.muted and clip.has_groove:
                reasons.append(
                    f"{clip.name} uses a groove. Render it to audio in Live first."
                )
            if clip.is_audio_clip:
                inventory["audioCandidates"] += 1
                markers: Any = clip.warp_markers
                marker_count += len(markers)
                if marker_count > CAPTURE_MAX_WARP_MARKERS:
                    raise ValueError("Too many warp markers for current-clips capture")
                clip_data.update(
                    {
                        "filePath": clip.file_path,
                        "gain": get_amplitude_from_decibels(clip.gain_display_string),
                        "warping": bool(clip.warping),
                        "pitch": get_capture_number(clip.pitch_coarse)
                        + get_capture_number(clip.pitch_fine) / 100,
                        "warpMarkers": [
                            {
                                "seconds": get_capture_number(marker.sample_time),
                                "beats": get_capture_number(marker.beat_time),
                            }
                            for marker in markers
                        ],
                    }
                )
            else:
                notes: Any = clip.get_notes_extended(0, 128, -8192.0, 32768.0)
                note_count += len(notes)
                if note_count > CAPTURE_MAX_NOTES:
                    raise ValueError("Too many MIDI notes for current-clips capture")
                clip_data["notes"] = [
                    {
                        "pitch": int(note.pitch),
                        "start": get_capture_number(note.start_time),
                        "duration": get_capture_number(note.duration),
                        "velocity": get_capture_number(note.velocity),
                        "muted": bool(note.mute),
                    }
                    for note in notes
                ]
                if audible and not clip.muted:
                    reasons.append(
                        f"{clip.name} is MIDI; Studio cannot render its Live instrument. Flatten or render it to audio first, mute the original, then retry. Save a Copy alone does not render instruments."
                    )
            clips.append(clip_data)
        if audible and any(not clip["muted"] for clip in clips):
            for output_index, output_track in enumerate(
                output_tracks[:captured_output_count]
            ):
                output_mixer: Any = output_track.mixer_device
                if output_track.devices:
                    reasons.append(
                        f"{output_track.name} has Live devices/effects. Render the track to audio first."
                    )
                if output_index == 0 and (
                    track.is_foldable
                    or track.is_grouped
                    or track.output_routing_type.display_name not in ("Master", "Main")
                ):
                    reasons.append(
                        f"{track.name} uses groups or custom routing. Render its output to audio first."
                    )
                if any(
                    get_capture_number(send.value) > 0 for send in output_mixer.sends
                ):
                    reasons.append(
                        f"{output_track.name} uses return sends. Render its output to audio first."
                    )
                if (
                    output_mixer.volume.automation_state
                    or output_mixer.panning.automation_state
                ):
                    reasons.append(
                        f"{output_track.name} has mixer automation. Render its output to audio first."
                    )
        tracks.append(
            {
                "index": track_index,
                "name": track.name,
                "muted": not audible,
                "solo": bool(track.solo),
                "armed": bool(track.arm) if track.can_be_armed else False,
                "volume": volume,
                "pan": get_capture_number(mixer.panning.value),
                # Live renders a frozen track's arrangement from its first clip onward.
                "freezeStartBeats": min(
                    (
                        get_capture_number(clip.start_time)
                        for clip in track.arrangement_clips
                    ),
                    default=None,
                )
                if getattr(track, "is_frozen", False) and not track.is_foldable
                else None,
                "instrumentClasses": [
                    str(device.class_name)
                    for device in track.devices
                    if getattr(device, "type", None) == 1
                    and not getattr(track, "is_frozen", False)
                ],
                "clips": clips,
            }
        )
    master: Any = song.master_track
    if master.devices:
        reasons.append(
            "The Main track has devices/effects. Render the mix to audio first."
        )
    if master.mixer_device.song_tempo.automation_state:
        reasons.append("Tempo automation needs a rendered audio context.")
    if (
        master.mixer_device.volume.automation_state
        or master.mixer_device.panning.automation_state
    ):
        reasons.append(
            "The Main track has mixer automation. Render the mix to audio first."
        )
    if get_capture_number(master.mixer_device.panning.value) != 0:
        reasons.append("The Main track has panning. Render the mix to audio first.")
    return {
        "version": CAPTURE_VERSION,
        "captureId": capture_id,
        "setInstanceId": set_id,
        "filePath": song.file_path or None,
        "range": {"startBeats": start, "endBeats": end},
        "tempo": get_capture_number(song.tempo),
        "timeSignature": {
            "numerator": int(song.signature_numerator),
            "denominator": int(song.signature_denominator),
        },
        "amplitude": get_mixer_amplitude(master.mixer_device.volume),
        "diagnostics": {
            **inventory,
            "returns": [
                {"index": index, "solo": bool(track.solo), "muted": bool(track.mute)}
                for index, track in enumerate(song.return_tracks)
            ],
        },
        "unsupported": list(dict.fromkeys(reasons)),
        "tracks": tracks,
    }


def export_current_clips(manager: Any, params: tuple[Any, ...]) -> tuple[Any, ...]:
    """Prepare Arrangement playback and publish a correlated immutable capture."""
    if len(params) != 5 or params[0] != CAPTURE_VERSION:
        raise ValueError("Repair Suno Bridge in Setup, restart Live, then retry Create")
    _, capture_id, expected_set_id, raw_start, raw_end = params
    if not isinstance(capture_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,80}", capture_id
    ):
        raise ValueError("Invalid current-clips capture request")
    start: float = get_capture_number(raw_start)
    end: float = get_capture_number(raw_end)
    if start < 0 or end <= start or end - start > 65536:
        raise ValueError("Choose a valid arrangement range, then retry")
    set_id: str = manager.get_live_set_id()
    if set_id != expected_set_id:
        raise ValueError("The Live Set changed; retry in the intended Set")
    song: Any = manager.song
    if song.back_to_arranger:
        if song.record_mode or song.session_record or any(
            clip.is_recording
            for track in song.tracks
            if not track.is_foldable
            for clip in track.arrangement_clips
        ) or any(
            slot.clip.is_recording
            for track in song.tracks
            for slot in track.clip_slots
            if slot.has_clip and slot.clip is not None
        ):
            raise ValueError("Stop recording, then retry current-clips capture.")
        song.back_to_arranger = False
        if song.back_to_arranger:
            raise ValueError("Live did not return to Arrangement playback. Retry Create.")
        if manager.get_live_set_id() != set_id:
            raise ValueError("The Live Set changed during capture; retry")
    native_tracks: tuple[Any, ...] = tuple(song.tracks)
    track_ids: list[str] = manager.get_live_track_ids()
    snapshot: dict[str, Any] = get_current_clips_snapshot(
        song, capture_id, set_id, start, end
    )
    if tuple(song.tracks) != native_tracks or len(track_ids) != len(snapshot["tracks"]):
        raise ValueError("The Live tracks changed during capture; retry")
    for track_data, identifier in zip(snapshot["tracks"], track_ids):
        track_data["id"] = identifier
    snapshot["setLinkId"] = manager.get_live_set_link_id()
    if manager.get_live_set_id() != set_id:
        raise ValueError("The Live Set changed during capture; retry")
    payload: bytes = json.dumps(
        snapshot, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    if len(payload) > CAPTURE_MAX_BYTES:
        raise ValueError("Current-clips capture is too large")
    output_dir: str = "/tmp" if sys.platform == "darwin" else tempfile.gettempdir()
    descriptor, output_path = tempfile.mkstemp(
        prefix=f"suno-link-capture-{capture_id}-", suffix=".json", dir=output_dir
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        os.unlink(output_path)
        raise
    return (
        CAPTURE_VERSION,
        capture_id,
        set_id,
        output_path,
        len(payload),
        hashlib.sha256(payload).hexdigest(),
    )

class SongHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "song"
        self.last_song_time: float = -1.0

    def init_api(self) -> None:
        #--------------------------------------------------------------------------------
        # Callbacks for Song: methods
        #--------------------------------------------------------------------------------
        for method in [
            "capture_and_insert_scene",
            "capture_midi",
            "continue_playing",
            "create_audio_track",
            "create_midi_track",
            "create_return_track",
            "create_scene",
            "delete_return_track",
            "delete_scene",
            "delete_track",
            "duplicate_scene",
            "duplicate_track",
            "force_link_beat_time",
            "jump_by",
            "jump_to_prev_cue",
            "jump_to_next_cue",
            "redo",
            "re_enable_automation",
            "set_or_delete_cue",
            "start_playing",
            "stop_all_clips",
            "stop_playing",
            "tap_tempo",
            "trigger_session_record",
            "undo"
        ]:
            callback = partial(self._call_method, self.song, method)
            self.osc_server.add_handler("/live/song/%s" % method, callback)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: properties (read/write)
        #--------------------------------------------------------------------------------
        properties_rw: List[str] = [
            "arrangement_overdub",
            "back_to_arranger",
            "clip_trigger_quantization",
            "current_song_time",
            "groove_amount",
            "is_ableton_link_enabled",
            "loop",
            "loop_length",
            "loop_start",
            "metronome",
            "midi_recording_quantization",
            "nudge_down",
            "nudge_up",
            "punch_in",
            "punch_out",
            "record_mode",
            "root_note",
            "scale_name",
            "session_record",
            "signature_denominator",
            "signature_numerator",
            "tempo"
        ]

        #--------------------------------------------------------------------------------
        # Callbacks for Song: properties (read-only)
        #--------------------------------------------------------------------------------
        properties_r: List[str] = [
            "can_redo",
            "can_undo",
            "file_path",
            "is_playing",
            "song_length",
            "session_record_status"
        ]

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/song/get/%s" % prop, partial(self._get_property, self.song, prop))
            self.osc_server.add_handler("/live/song/start_listen/%s" % prop, partial(self._start_listen, self.song, prop))
            self.osc_server.add_handler("/live/song/stop_listen/%s" % prop, partial(self._stop_listen, self.song, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/song/set/%s" % prop, partial(self._set_property, self.song, prop))

        #--------------------------------------------------------------------------------
        # The first two values retain the saved-path/count wire contract. Identity
        # lives on Manager so reloading handlers does not create another set token.
        #--------------------------------------------------------------------------------
        def song_get_connection_state(_: Any) -> Tuple[Any, ...]:
            return self.manager.get_live_set_state()
        self.osc_server.add_handler("/live/song/get/connection_state", song_get_connection_state)

        #--------------------------------------------------------------------------------
        # /live/song/create_{audio,midi}_track_with_config — atomic create + name + color.
        # Args: (insert_at, [name], [color]). Returns (new_index,).
        #
        # The plain /live/song/create_*_track endpoints don't echo a reply with the new
        # index, forcing callers to follow up with /live/song/get/num_tracks and assume
        # the latest is theirs (racy with concurrent edits). This single-shot variant
        # creates the track, optionally sets its name and 24-bit RGB color, and replies
        # with the resolved index of the new track.
        #--------------------------------------------------------------------------------
        def make_create_track_with_config(create_method_name: str) -> Any:
            def callback(params: Tuple[Any, ...]) -> Tuple[Any, ...]:
                insert_at: int = int(params[0]) if len(params) >= 1 else -1
                name: Optional[str] = params[1] if len(params) >= 2 else None
                color: Optional[int] = int(params[2]) if len(params) >= 3 else None
                studio_track_id: Optional[str] = str(UUID(str(params[3]))) if len(params) >= 4 else None

                create_method = getattr(self.song, create_method_name)
                pre_count: int = len(self.song.tracks)
                new_track: Any = create_method(insert_at)
                # The Live Object Model declares create_audio_track/create_midi_track
                # as returning Live.Track.Track, but some Live versions return None.
                # Resolve the new index from the inserted position when the return
                # value is unusable, so we never crash on .index(None).
                tracks: List[Any] = list(self.song.tracks)
                if new_track is not None and new_track in tracks:
                    new_index: int = tracks.index(new_track)
                else:
                    if insert_at < 0 or insert_at >= pre_count:
                        new_index = len(tracks) - 1
                    else:
                        new_index = insert_at
                    new_track = tracks[new_index]
                if name:
                    new_track.name = name
                if color is not None and color >= 0:
                    new_track.color = color
                if studio_track_id is not None:
                    self.manager.get_live_track_id(new_track, studio_track_id)
                return (new_index,)
            return callback

        self.osc_server.add_handler(
            "/live/song/create_audio_track_with_config",
            make_create_track_with_config("create_audio_track"))
        self.osc_server.add_handler(
            "/live/song/create_midi_track_with_config",
            make_create_track_with_config("create_midi_track"))

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Track properties
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_tracks", lambda _: (len(self.song.tracks),))

        def song_get_track_names(params: Tuple[Any, ...]) -> Tuple[Any, ...]:
            if len(params) == 0:
                track_index_min, track_index_max = 0, len(self.song.tracks)
            else:
                track_index_min, track_index_max = params
                if track_index_max == -1:
                    track_index_max = len(self.song.tracks)
            return tuple(self.song.tracks[index].name for index in range(track_index_min, track_index_max))
        self.osc_server.add_handler("/live/song/get/track_names", song_get_track_names)

        def song_get_track_data(params: Tuple[Any, ...]) -> Tuple[Any, ...]:
            """
            Retrieve one more properties of a block of tracks and their clips.
            Properties must be of the format track.property_name or clip.property_name.

            For example:
                /live/song/get/track_data 0 12 track.name clip.name clip.length

            Queries tracks 0..11, and returns a list of values comprising:

            [track_0_name, clip_0_0_name,   clip_0_1_name,   ... clip_0_7_name,
                           clip_1_0_length, clip_0_1_length, ... clip_0_7_length,
             track_1_name, clip_1_0_name,   clip_1_1_name,   ... clip_1_7_name, ...]
            """
            track_index_min, track_index_max, *properties = params
            track_index_min = int(track_index_min)
            track_index_max = int(track_index_max)
            self.logger.info("Getting track data: %s (tracks %d..%d)" %
                             (properties, track_index_min, track_index_max))
            if track_index_max == -1:
                track_index_max = len(self.song.tracks)
            rv: List[Any] = []
            for track_index in range(track_index_min, track_index_max):
                track: Any = self.song.tracks[track_index]
                for prop in properties:
                    obj: str
                    property_name: str
                    obj, property_name = prop.split(".")
                    if obj == "track":
                        if property_name == "num_devices":
                            value: Any = len(track.devices)
                        else:
                            value = getattr(track, property_name)
                            if isinstance(value, Live.Track.Track):
                                #--------------------------------------------------------------------------------
                                # Map Track objects to their track_index to return via OSC
                                #--------------------------------------------------------------------------------
                                value = list(self.song.tracks).index(value)
                        rv.append(value)
                    elif obj == "clip":
                        for clip_slot in track.clip_slots:
                            if clip_slot.clip is not None:
                                rv.append(getattr(clip_slot.clip, property_name))
                            else:
                                rv.append(None)
                    elif obj == "clip_slot":
                        for clip_slot in track.clip_slots:
                            rv.append(getattr(clip_slot, property_name))
                    elif obj == "device":
                        for device in track.devices:
                            rv.append(getattr(device, property_name))
                    else:
                        self.logger.error("Unknown object identifier in get/track_data: %s" % obj)
            return tuple(rv)
        self.osc_server.add_handler("/live/song/get/track_data", song_get_track_data)


        def song_export_structure(params: Tuple[Any, ...]) -> Tuple[Any, ...]:
            if params:
                return export_current_clips(self.manager, params)
            tracks: List[Any] = []
            for track_index, track in enumerate(self.song.tracks):
                group_track: Optional[int] = None
                if track.group_track is not None:
                    group_track = list(self.song.tracks).index(track.group_track)
                track_data: Any = {
                    "index": track_index,
                    "name": track.name,
                    "is_foldable": track.is_foldable,
                    "group_track": group_track,
                    "clips": [],
                    "devices": []
                }
                for clip_index, clip_slot in enumerate(track.clip_slots):
                    if clip_slot.clip:
                        clip_data: Any = {
                            "index": clip_index,
                            "name": clip_slot.clip.name,
                            "length": clip_slot.clip.length,
                        }
                        track_data["clips"].append(clip_data)

                for device_index, device in enumerate(track.devices):
                    device_data: Any = {
                        "class_name": device.class_name,
                        "type": device.type,
                        "name": device.name,
                        "parameters": []
                    }
                    for parameter in device.parameters:
                        device_data["parameters"].append({
                            "name": parameter.name,
                            "value": parameter.value,
                            "min": parameter.min,
                            "max": parameter.max,
                            "is_quantized": parameter.is_quantized,
                        })
                    track_data["devices"].append(device_data)

                tracks.append(track_data)
            song: Any = {
                "tracks": tracks
            }

            # On macOS, tempfile.gettempdir() resolves to a process-specific
            # directory other processes can't easily discover. Use /tmp there
            # so external consumers know where to read the export. On other
            # platforms, defer to tempfile.gettempdir(). Avoid mutating
            # os.environ — Live shares the Python process across remote
            # scripts, so a permanent TMPDIR change leaks globally.
            output_dir: str = "/tmp" if sys.platform == "darwin" else tempfile.gettempdir()
            output_path: str = os.path.join(output_dir, "suno_control-song-structure.json")
            with open(output_path, "w") as fd:
                json.dump(song, fd)
            self.logger.warning("Exported song structure to %s" % output_path)
            return (1,)
        self.osc_server.add_handler("/live/song/export/structure", song_export_structure)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Scene properties
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_scenes", lambda _: (len(self.song.scenes),))

        def song_get_scene_names(params: Tuple[Any, ...]) -> Tuple[Any, ...]:
            if len(params) == 0:
                scene_index_min, scene_index_max = 0, len(self.song.scenes)
            else:
                scene_index_min, scene_index_max = params
            return tuple(self.song.scenes[index].name for index in range(scene_index_min, scene_index_max))
        self.osc_server.add_handler("/live/song/get/scenes/name", song_get_scene_names)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Cue point properties
        #--------------------------------------------------------------------------------
        def song_get_cue_points(song: Any, _: Any) -> Tuple[Any, ...]:
            cue_points: Any = song.cue_points
            cue_point_pairs: List[Tuple[Any, Any]] = [(cue_point.name, cue_point.time) for cue_point in cue_points]
            return tuple(element for pair in cue_point_pairs for element in pair)
        self.osc_server.add_handler("/live/song/get/cue_points", partial(song_get_cue_points, self.song))

        def song_jump_to_cue_point(song: Any, params: Tuple[Any, ...] = ()) -> None:
            cue_point_index: Any = params[0]
            if isinstance(cue_point_index, str):
                for cp in song.cue_points:
                    if cp.name == cue_point_index:
                        cp.jump()
            elif isinstance(cue_point_index, int):
                cue_point: Any = song.cue_points[cue_point_index]
                cue_point.jump()
        self.osc_server.add_handler("/live/song/cue_point/jump", partial(song_jump_to_cue_point, self.song))

        self.osc_server.add_handler("/live/song/cue_point/add_or_delete", partial(self._call_method, self.song, "set_or_delete_cue"))
        def song_cue_point_set_name(song: Any, params: Tuple[Any, ...] = ()) -> None:
            cue_point_index: int = params[0]
            new_name: str = params[1]
            cue_point: Any = song.cue_points[cue_point_index]
            cue_point.name = new_name
        self.osc_server.add_handler("/live/song/cue_point/set/name", partial(song_cue_point_set_name, self.song))

        #--------------------------------------------------------------------------------
        # Listener for /live/song/get/beat
        #--------------------------------------------------------------------------------
        self.last_song_time = -1.0

        def stop_beat_listener(params: Tuple[Any, ...] = ()) -> None:
            try:
                self.song.remove_current_song_time_listener(self.current_song_time_changed)
                self.logger.info("Removing beat listener")
            except Exception:
                pass

        def start_beat_listener(params: Tuple[Any, ...] = ()) -> None:
            stop_beat_listener()
            self.logger.info("Adding beat listener")
            self.song.add_current_song_time_listener(self.current_song_time_changed)

        self.osc_server.add_handler("/live/song/start_listen/beat", start_beat_listener)
        self.osc_server.add_handler("/live/song/stop_listen/beat", stop_beat_listener)

    def current_song_time_changed(self) -> None:
        # On rewind, or when crossing into a new integer beat, emit a
        # /live/song/get/beat message so subscribed clients track transport.
        if (self.song.current_song_time < self.last_song_time) or \
                (int(self.song.current_song_time) > int(self.last_song_time)):
            self.osc_server.send("/live/song/get/beat", (int(self.song.current_song_time),))
        self.last_song_time = self.song.current_song_time

    def clear_api(self) -> None:
        super().clear_api()
        try:
            self.song.remove_current_song_time_listener(self.current_song_time_changed)
        except Exception:
            pass
