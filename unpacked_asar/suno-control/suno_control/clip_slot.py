from __future__ import annotations

from typing import Tuple, Any, Callable, Optional, List
from .handler import AbletonOSCHandler

class ClipSlotHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "clip_slot"

    def init_api(self) -> None:
        def create_clip_slot_callback(func: Callable[..., Any], *args: Any, pass_clip_index: bool = False) -> Callable[[Tuple[Any, ...]], Optional[Tuple[Any, ...]]]:
            def clip_slot_callback(params: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
                track_index: int = int(params[0])
                clip_index: int = int(params[1])
                track: Any = self.song.tracks[track_index]
                clip_slot: Any = track.clip_slots[clip_index]

                if pass_clip_index:
                    rv: Any = func(clip_slot, *args, tuple(params[0:]))
                else:
                    rv = func(clip_slot, *args, tuple(params[2:]))

                self.logger.info("clip_slot callback: track=%s clip=%s rv=%s", track_index, clip_index, rv)
                if rv is not None:
                    return (track_index, clip_index, *rv)
                return None

            return clip_slot_callback

        methods: List[str] = [
            "fire",
            "stop",
            "create_clip",
            "delete_clip"
        ]
        properties_r: List[str] = [
            "has_clip",
            "controls_other_clips",
            "is_group_slot",
            "is_playing",
            "is_triggered",
            "playing_status",
            "will_record_on_start",
        ]
        properties_rw: List[str] = [
            "has_stop_button"
        ]

        for method in methods:
            self.osc_server.add_handler("/live/clip_slot/%s" % method,
                                        create_clip_slot_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/clip_slot/get/%s" % prop,
                                        create_clip_slot_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/clip_slot/start_listen/%s" % prop,
                                        create_clip_slot_callback(self._start_listen, prop, pass_clip_index=True))
            self.osc_server.add_handler("/live/clip_slot/stop_listen/%s" % prop,
                                        create_clip_slot_callback(self._stop_listen, prop, pass_clip_index=True))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/clip_slot/set/%s" % prop,
                                        create_clip_slot_callback(self._set_property, prop))

        def duplicate_clip_slot(clip_slot: Any, args: Tuple[Any, ...]) -> None:
            # OSC clients (TouchOSC, etc.) often send numeric args as floats —
            # cast to int so list indexing doesn't TypeError.
            target_track_index: int = int(args[0])
            target_clip_index: int = int(args[1])
            track: Any = self.song.tracks[target_track_index]
            target_clip_slot: Any = track.clip_slots[target_clip_index]
            clip_slot.duplicate_clip_to(target_clip_slot)

        self.osc_server.add_handler("/live/clip_slot/duplicate_clip_to", create_clip_slot_callback(duplicate_clip_slot))
