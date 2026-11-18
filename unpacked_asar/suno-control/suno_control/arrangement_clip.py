"""
Arrangement-clip handler — parallel to clip.py but resolves clips via
`track.arrangement_clips[clip_index]` instead of `track.clip_slots[clip_index].clip`.

The existing /live/clip/* family is session-view only because of how it
resolves the target Clip. The arrangement view has its own clip collection
on each Track (`track.arrangement_clips`), and the LOM exposes the same
property surface on those Clip objects. This handler exposes that surface at
/live/arrangement_clip/* so callers can address and configure clips created
by /live/track/create_audio_clip without dropping into session-view slots.

OSC addressing:

    /live/arrangement_clip/get/<prop>             (track, clip)
    /live/arrangement_clip/set/<prop>             (track, clip, value)
    /live/arrangement_clip/start_listen/<prop>    (track, clip)
    /live/arrangement_clip/stop_listen/<prop>     (track, clip)
    /live/arrangement_clip/delete                 (track, clip)

`clip` here is the index into `track.arrangement_clips`, which Live keeps
sorted by `start_time`. Inserting or deleting a clip can shift indices of
later clips on the same track, so callers that hold an index across mutations
should re-resolve via `/live/track/get/arrangement_clips/start_time`.
"""
from __future__ import annotations

from typing import Tuple, Callable, Any, Optional, List
from .handler import AbletonOSCHandler


class ArrangementClipHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "arrangement_clip"

    def init_api(self) -> None:
        def create_arrangement_clip_callback(
            func: Callable[..., Any],
            *args: Any,
            pass_clip_index: bool = False,
        ) -> Callable[[Tuple[Any, ...]], Optional[Tuple[Any, ...]]]:
            """
            Build a callback that resolves (track_index, clip_index, *rest) to
            the matching Clip in `track.arrangement_clips` and invokes `func`
            with that Clip plus the remaining params.

            Mirrors clip.py's create_clip_callback. `pass_clip_index=True` is
            the same escape hatch: the inner func needs the indices to route
            listener updates back to the right address.
            """
            def arrangement_clip_callback(
                params: Tuple[Any, ...],
            ) -> Optional[Tuple[Any, ...]]:
                track_index: int = int(params[0])
                clip_index: int = int(params[1])
                track: Any = self.song.tracks[track_index]
                # `arrangement_clips` is a Live tuple-like; index access raises
                # IndexError on overflow — let it propagate, the OSC server
                # surface translates exceptions into /live/error.
                clip: Any = track.arrangement_clips[clip_index]
                if pass_clip_index:
                    rv: Any = func(clip, *args, tuple(params[0:]))
                else:
                    rv = func(clip, *args, tuple(params[2:]))

                if rv is not None:
                    return (track_index, clip_index, *rv)
                return None

            return arrangement_clip_callback

        # Property surface mirrors clip.py. The LOM exposes the same field set
        # on both session and arrangement Clip objects, so we don't filter —
        # callers that hit a property that doesn't apply to audio arrangement
        # clips (e.g. MIDI-only) will see a Live-side error, same as today on
        # /live/clip/*.
        properties_r: List[str] = [
            "end_time",
            "file_path",
            "gain_display_string",
            "has_groove",
            "is_midi_clip",
            "is_audio_clip",
            "is_overdubbing",
            "is_playing",
            "is_recording",
            "is_triggered",
            "length",
            "playing_position",
            "sample_length",
            "start_time",
            "will_record_on_start",
        ]
        properties_rw: List[str] = [
            "color",
            "color_index",
            "end_marker",
            "gain",
            "launch_mode",
            "launch_quantization",
            "legato",
            "loop_end",
            "loop_start",
            "looping",
            "muted",
            "name",
            "pitch_coarse",
            "pitch_fine",
            "position",
            "ram_mode",
            "start_marker",
            "velocity_amount",
            "warp_mode",
            "warping",
        ]

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler(
                "/live/arrangement_clip/get/%s" % prop,
                create_arrangement_clip_callback(self._get_property, prop),
            )
            self.osc_server.add_handler(
                "/live/arrangement_clip/start_listen/%s" % prop,
                create_arrangement_clip_callback(
                    self._start_listen, prop, pass_clip_index=True
                ),
            )
            self.osc_server.add_handler(
                "/live/arrangement_clip/stop_listen/%s" % prop,
                create_arrangement_clip_callback(
                    self._stop_listen, prop, pass_clip_index=True
                ),
            )
        for prop in properties_rw:
            self.osc_server.add_handler(
                "/live/arrangement_clip/set/%s" % prop,
                create_arrangement_clip_callback(self._set_property, prop),
            )

        def arrangement_clip_delete(clip: Any, _: Tuple[Any, ...]) -> Tuple[str, ...]:
            # `track.delete_clip(clip)` is the LOM call — Clip.delete() doesn't
            # exist for arrangement clips. The Track owns the lifecycle.
            track: Any = clip.canonical_parent
            track.delete_clip(clip)
            return ("ok",)

        self.osc_server.add_handler(
            "/live/arrangement_clip/delete",
            create_arrangement_clip_callback(arrangement_clip_delete),
        )
