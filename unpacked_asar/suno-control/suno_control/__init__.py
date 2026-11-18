from __future__ import annotations

import logging
from functools import partial
from typing import Any, List, Optional, Tuple

import Live

logger: logging.Logger = logging.getLogger("suno_control")
logger.info("Reloading suno_control...")

from .osc_server import OSCServer, OSC_LISTEN_PORT, OSC_RESPONSE_PORT
from .handler import AbletonOSCHandler
from .song import SongHandler
from .clip import ClipHandler
from .clip_slot import ClipSlotHandler
from .track import TrackHandler
from .device import DeviceHandler
from .scene import SceneHandler
from .browser import BrowserHandler
from .arrangement_clip import ArrangementClipHandler

__all__ = [
    "OSCServer",
    "OSC_LISTEN_PORT",
    "OSC_RESPONSE_PORT",
    "AbletonOSCHandler",
    "SongHandler",
    "ClipHandler",
    "ClipSlotHandler",
    "TrackHandler",
    "DeviceHandler",
    "SceneHandler",
    "BrowserHandler",
    "ArrangementClipHandler",
]


#--------------------------------------------------------------------------------
# ApplicationHandler
#--------------------------------------------------------------------------------

class ApplicationHandler(AbletonOSCHandler):
    def init_api(self) -> None:
        def get_version(_: Any) -> Tuple[Any, ...]:
            application: Any = Live.Application.get_application()
            return application.get_major_version(), application.get_minor_version()
        self.osc_server.add_handler("/live/application/get/version", get_version)
        self.osc_server.send("/live/startup")

        def get_average_process_usage(_: Any) -> Tuple[Any, ...]:
            application: Any = Live.Application.get_application()
            return application.average_process_usage,
        self.osc_server.add_handler("/live/application/get/average_process_usage", get_average_process_usage)


#--------------------------------------------------------------------------------
# ViewHandler
#--------------------------------------------------------------------------------

class ViewHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "view"

    def init_api(self) -> None:
        def get_selected_scene(params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
            return (list(self.song.scenes).index(self.song.view.selected_scene),)

        def get_selected_track(params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
            # song.view.selected_track can be a return or master track, which
            # are NOT in song.tracks. Return -1 to signal "not a regular track"
            # rather than letting list.index() raise ValueError and erroring
            # the OSC response.
            tracks: List[Any] = list(self.song.tracks)
            selected: Any = self.song.view.selected_track
            if selected in tracks:
                return (tracks.index(selected),)
            return (-1,)

        def get_selected_clip(params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
            return (get_selected_track()[0], get_selected_scene()[0])

        def get_selected_device(params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
            return (get_selected_track()[0], list(self.song.view.selected_track.devices).index(self.song.view.selected_track.view.selected_device))

        def set_selected_scene(params: Optional[Tuple[Any, ...]] = ()) -> None:
            self.song.view.selected_scene = self.song.scenes[int(params[0])]

        def set_selected_track(params: Optional[Tuple[Any, ...]] = ()) -> None:
            self.song.view.selected_track = self.song.tracks[int(params[0])]

        def set_selected_clip(params: Optional[Tuple[Any, ...]] = ()) -> None:
            set_selected_track((params[0],))
            set_selected_scene((params[1],))

        def set_selected_device(params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
            track_index: int = int(params[0])
            device_index: int = int(params[1])
            device: Any = self.song.tracks[track_index].devices[device_index]
            self.song.view.select_device(device)
            return track_index, device_index

        self.osc_server.add_handler("/live/view/get/selected_scene", get_selected_scene)
        self.osc_server.add_handler("/live/view/get/selected_track", get_selected_track)
        self.osc_server.add_handler("/live/view/get/selected_clip", get_selected_clip)
        self.osc_server.add_handler("/live/view/get/selected_device", get_selected_device)
        self.osc_server.add_handler("/live/view/set/selected_scene", set_selected_scene)
        self.osc_server.add_handler("/live/view/set/selected_track", set_selected_track)
        self.osc_server.add_handler("/live/view/set/selected_clip", set_selected_clip)
        self.osc_server.add_handler("/live/view/set/selected_device", set_selected_device)

        self.osc_server.add_handler('/live/view/start_listen/selected_scene', partial(self._start_listen, self.song.view, "selected_scene", getter=get_selected_scene))
        self.osc_server.add_handler('/live/view/start_listen/selected_track', partial(self._start_listen, self.song.view, "selected_track", getter=get_selected_track))
        self.osc_server.add_handler('/live/view/stop_listen/selected_scene', partial(self._stop_listen, self.song.view, "selected_scene"))
        self.osc_server.add_handler('/live/view/stop_listen/selected_track', partial(self._stop_listen, self.song.view, "selected_track"))


#--------------------------------------------------------------------------------
# MidiMapHandler
#--------------------------------------------------------------------------------

class MidiMapHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "midimap"
        self.midi_map_handle: Optional[Any] = None

    def init_api(self) -> None:
        def make_midi_map(params: Tuple[Any, ...] = ()) -> None:
            track_index: int = int(params[0])
            device_index: int = int(params[1])
            parameter_index: int = int(params[2])
            channel: int = int(params[3])
            cc: int = int(params[4])

            parameter: Any = self.song.tracks[track_index].devices[device_index].parameters[parameter_index]
            self.manager.midi_mappings[(channel, cc)] = parameter

            self.manager.request_rebuild_midi_map()

        self.osc_server.add_handler("/live/midimap/map_cc", make_midi_map)
