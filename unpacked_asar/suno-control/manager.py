from __future__ import annotations

import importlib
import logging
import os
import traceback
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import Live
from ableton.v2.base import liveobj_changed, liveobj_valid
from ableton.v2.control_surface import ControlSurface

from . import suno_control

logger: logging.Logger = logging.getLogger("suno_control")

class Manager(ControlSurface):
    def __init__(self, c_instance: Any) -> None:
        ControlSurface.__init__(self, c_instance)

        self.log_level: str = "info"

        self.handlers: List[Any] = []
        self.midi_mappings: Dict[Tuple[int, int], Any] = {}
        self._live_set_identity: Optional[Tuple[Any, str]] = None
        self._live_track_identities: list[tuple[Any, str]] = []
        # None until startup succeeds. Startup can fail before these are
        # assigned (port 11000 already bound by another Live instance), and
        # Live still calls disconnect() on unload, so teardown must handle
        # the None state.
        self.osc_server: Optional[suno_control.OSCServer] = None
        self.log_file_handler: Optional[logging.FileHandler] = None
        self.live_osc_error_handler: Optional[logging.StreamHandler] = None

        try:
            self.osc_server = suno_control.OSCServer(get_live_set_id=self.get_live_set_id)
            self.schedule_message(0, self.tick)

            self.start_logging()
            self.init_api()

            self.show_message("Suno Bridge: Listening for OSC on port %d" % suno_control.OSC_LISTEN_PORT)
            logger.info("Started Suno Bridge on address %s" % str(self.osc_server._local_addr))
        except OSError as msg:
            self.show_message("Suno Bridge: Couldn't bind to port %d (%s)" % (suno_control.OSC_LISTEN_PORT, msg))
            logger.info("Couldn't bind to port %d (%s)" % (suno_control.OSC_LISTEN_PORT, msg))


    def get_live_set_id(self) -> str:
        """Read the current Song token without scanning its clips."""
        song: Any = self.song
        if not liveobj_valid(song):
            raise RuntimeError("The current Live Set is unavailable")
        previous: Optional[Tuple[Any, str]] = self._live_set_identity
        identity: Tuple[Any, str]
        if previous is None or liveobj_changed(previous[0], song):
            identity = (song, str(uuid4()))
            self._live_set_identity = identity
            self._live_track_identities = []
        else:
            identity = previous
        return identity[1]

    def get_live_set_link_id(self) -> str:
        """Read the persisted Bridge namespace owned by the native Song."""
        self.get_live_set_id()
        value: Any = self.song.get_data("suno-link-set-id", None)
        try:
            return str(UUID(value))
        except (ValueError, TypeError, AttributeError):
            identity = str(uuid4())
            self.song.set_data("suno-link-set-id", identity)
            return identity

    def get_live_track_id(
        self, track: Any, studio_track_id: str | None = None
    ) -> str:
        """Store Studio associations on native Tracks and reject ambiguous copies."""
        self.get_live_set_link_id()
        tracks: list[Any] = list(self.song.tracks)
        if not liveobj_valid(track) or not any(
            not liveobj_changed(track, candidate) for candidate in tracks
        ):
            raise ValueError("The Live track is unavailable")
        identities: list[tuple[Any, str]] = []
        for candidate in tracks:
            value: Any = candidate.get_data("suno-link-studio-track-id", None)
            try:
                identifier = str(UUID(value))
            except (ValueError, TypeError, AttributeError):
                identifier = str(uuid4())
                candidate.set_data("suno-link-studio-track-id", identifier)
            identities.append((candidate, identifier))
        counts: dict[str, int] = {}
        for _, identifier in identities:
            counts[identifier] = counts.get(identifier, 0) + 1
        duplicates = {identifier for identifier, count in counts.items() if count > 1}
        for duplicate in duplicates:
            owners = [
                native
                for native, identifier in self._live_track_identities
                if identifier == duplicate
                and any(not liveobj_changed(native, candidate) for candidate in tracks)
            ]
            if len(owners) != 1:
                # Copied Track data cannot prove which native object owns saved processing.
                self.song.set_data("suno-link-set-id", str(uuid4()))
                identities = [(candidate, str(uuid4())) for candidate in tracks]
                break
            identities = [
                (
                    candidate,
                    str(uuid4())
                    if identifier == duplicate and liveobj_changed(candidate, owners[0])
                    else identifier,
                )
                for candidate, identifier in identities
            ]
        if studio_track_id is not None:
            studio_track_id = str(UUID(studio_track_id))
            if any(
                identifier == studio_track_id and liveobj_changed(candidate, track)
                for candidate, identifier in identities
            ):
                studio_track_id = str(uuid4())
            identities = [
                (
                    candidate,
                    studio_track_id
                    if not liveobj_changed(candidate, track)
                    else identifier,
                )
                for candidate, identifier in identities
            ]
        for candidate, identifier in identities:
            if candidate.get_data("suno-link-studio-track-id", None) != identifier:
                candidate.set_data("suno-link-studio-track-id", identifier)
        self._live_track_identities = identities
        return next(
            identifier
            for candidate, identifier in identities
            if not liveobj_changed(candidate, track)
        )

    def get_live_track_ids(self) -> list[str]:
        """Read and validate persistent Track data once for the whole capture."""
        tracks: list[Any] = list(self.song.tracks)
        if not tracks:
            return []
        self.get_live_track_id(tracks[0])
        return [identifier for _, identifier in self._live_track_identities]

    def get_live_set_state(self) -> tuple[str, int, str, str]:
        """Read the current Song identity in one native callback."""
        identity = self.get_live_set_id()
        song: Any = self.song
        tracks: Any = song.tracks
        try:
            namespace = str(UUID(song.get_data("suno-link-set-id", None)))
        except (ValueError, TypeError, AttributeError):
            namespace = ""
        except Exception:
            logger.debug("Live Set namespace is unavailable", exc_info=True)
            namespace = ""
        return (
            getattr(song, "file_path", "") or "",
            len(tracks),
            identity,
            namespace,
        )

    def start_logging(self) -> None:
        """
        Start logging to a local logfile (logs/suno_control.log),
        and relay error messages via OSC.
        """
        module_path: str = os.path.dirname(os.path.realpath(__file__))
        log_dir: str = os.path.join(module_path, "logs")
        if not os.path.exists(log_dir):
            os.mkdir(log_dir, 0o755)
        log_path: str = os.path.join(log_dir, "suno_control.log")
        self.log_file_handler = logging.FileHandler(log_path)
        self.log_file_handler.setLevel(self.log_level.upper())
        formatter: logging.Formatter = logging.Formatter('(%(asctime)s) [%(levelname)s] %(message)s')
        self.log_file_handler.setFormatter(formatter)
        logger.addHandler(self.log_file_handler)

        class LiveOSCErrorLogHandler(logging.StreamHandler):
            def emit(handler, record: logging.LogRecord) -> None:
                message: str = record.getMessage()
                if ":" in message:
                    message = message[message.index(":") + 2:]
                try:
                    self.osc_server.send("/live/error", (message,))
                except OSError:
                    # If the connection is dead, silently ignore errors as there's not much more we can do
                    pass
        self.live_osc_error_handler = LiveOSCErrorLogHandler()
        self.live_osc_error_handler.setLevel(logging.ERROR)
        logger.addHandler(self.live_osc_error_handler)

    def stop_logging(self) -> None:
        """
        Remove the log handlers installed by start_logging. Safe to call when
        startup failed before start_logging ran.
        """
        if self.log_file_handler is not None:
            logger.removeHandler(self.log_file_handler)
            self.log_file_handler = None
        if self.live_osc_error_handler is not None:
            logger.removeHandler(self.live_osc_error_handler)
            self.live_osc_error_handler = None

    def init_api(self) -> None:
        def test_callback(params: Any) -> None:
            self.show_message("Received OSC OK")
            self.osc_server.send("/live/test", ("ok",))
        def ping_callback(params: Any) -> Tuple[str, ...]:
            # Quiet liveness probe — no show_message side effect. Clients that
            # poll Ableton liveness on a timer should hit /live/ping instead of
            # /live/test so the status bar doesn't flicker "Received OSC OK"
            # forever.
            return ("ok",)
        def reload_callback(params: Any) -> None:
            self.reload_imports()
        def get_log_level_callback(params: Any) -> Tuple[str, ...]:
            return (self.log_level,)
        def set_log_level_callback(params: Any) -> None:
            log_level: str = params[0]
            assert log_level in ("debug", "info", "warning", "error", "critical")
            self.log_level = log_level
            self.log_file_handler.setLevel(self.log_level.upper())
        def show_message_callback(params: Any) -> None:
            self.show_message(params[0])

        self.osc_server.add_handler("/live/test", test_callback)
        self.osc_server.add_handler("/live/ping", ping_callback)
        self.osc_server.add_handler("/live/api/reload", reload_callback)
        self.osc_server.add_handler("/live/api/get/log_level", get_log_level_callback)
        self.osc_server.add_handler("/live/api/set/log_level", set_log_level_callback)
        self.osc_server.add_handler("/live/api/show_message", show_message_callback)

        with self.component_guard():
            self.handlers = [
                suno_control.SongHandler(self),
                suno_control.ApplicationHandler(self),
                suno_control.ClipHandler(self),
                suno_control.ClipSlotHandler(self),
                suno_control.TrackHandler(self),
                suno_control.DeviceHandler(self),
                suno_control.ViewHandler(self),
                suno_control.SceneHandler(self),
                suno_control.MidiMapHandler(self),
                suno_control.BrowserHandler(self),
                suno_control.ArrangementClipHandler(self),
            ]

    def clear_api(self) -> None:
        self.osc_server.clear_handlers()
        for handler in self.handlers:
            handler.clear_api()

    def tick(self) -> None:
        """
        Called once per 100ms "tick".
        Live's embedded Python implementation does not appear to support threading,
        and beachballs when a thread is started. Instead, this approach allows long-running
        processes such as the OSC server to perform operations.
        """
        logger.debug("Tick...")
        try:
            self.osc_server.process()
        finally:
            self.schedule_message(1, self.tick)

    def reload_imports(self) -> None:
        try:
            importlib.reload(suno_control.clip)
            importlib.reload(suno_control.clip_slot)
            importlib.reload(suno_control.device)
            importlib.reload(suno_control.handler)
            importlib.reload(suno_control.osc_server)
            importlib.reload(suno_control.scene)
            importlib.reload(suno_control.song)
            importlib.reload(suno_control.track)
            importlib.reload(suno_control.browser)
            importlib.reload(suno_control.arrangement_clip)
            importlib.reload(suno_control)
        except Exception:
            exc: str = traceback.format_exc()
            logger.warning(exc)

        self.clear_api()
        self.init_api()
        logger.info("Reloaded code")

    def disconnect(self) -> None:
        """
        Tear down logging and the OSC server on control-surface unload. Live
        calls this even when startup failed, so a None osc_server is expected.
        """
        self.show_message("Disconnecting...")
        logger.info("Disconnecting...")
        self.stop_logging()
        if self.osc_server is not None:
            self.osc_server.shutdown()
        super().disconnect()

    def build_midi_map(self, midi_map_handle: Any) -> None:
        """
        Called by Live to build the MIDI map.
        """
        logger.debug("Building MIDI map...")

        channel: int
        cc: int
        for channel, cc in self.midi_mappings.keys():
            parameter: Any = self.midi_mappings[(channel, cc)]
            Live.MidiMap.map_midi_cc(midi_map_handle, parameter, channel, cc, Live.MidiMap.MapMode.absolute, 1)
            logger.debug("Mapped CC %d on channel %d to parameter %s" % (cc, channel, parameter.name))
