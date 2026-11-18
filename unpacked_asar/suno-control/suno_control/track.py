from __future__ import annotations

import os
from typing import Tuple, Any, Callable, Optional, List
from .handler import AbletonOSCHandler


class TrackHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "track"

    def init_api(self) -> None:
        def create_track_callback(func: Callable[..., Any],
                                  *args: Any,
                                  include_track_id: bool = False) -> Callable[[Tuple[Any, ...]], Optional[Tuple[Any, ...]]]:
            def track_callback(params: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
                if params[0] == "*":
                    track_indices: List[int] = list(range(len(self.song.tracks)))
                else:
                    track_indices = [int(params[0])]

                rv: Any = None
                for track_index in track_indices:
                    track: Any = self.song.tracks[track_index]
                    if include_track_id:
                        rv = func(track, *args, tuple([track_index] + list(params[1:])))
                    else:
                        rv = func(track, *args, tuple(params[1:]))

                    if rv is not None:
                        return (track_index, *rv)
                return None

            return track_callback

        methods: List[str] = [
            "delete_device",
            "stop_all_clips"
        ]
        properties_r: List[str] = [
            "can_be_armed",
            "fired_slot_index",
            "has_audio_input",
            "has_audio_output",
            "has_midi_input",
            "has_midi_output",
            "is_foldable",
            "is_grouped",
            "is_visible",
            "output_meter_level",
            "output_meter_left",
            "output_meter_right",
            "playing_slot_index",
        ]
        properties_rw: List[str] = [
            "arm",
            "color",
            "color_index",
            "current_monitoring_state",
            "fold_state",
            "mute",
            "solo",
            "name"
        ]

        for method in methods:
            self.osc_server.add_handler("/live/track/%s" % method,
                                        create_track_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/track/get/%s" % prop,
                                        create_track_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/track/start_listen/%s" % prop,
                                        create_track_callback(self._start_listen, prop, include_track_id=True))
            self.osc_server.add_handler("/live/track/stop_listen/%s" % prop,
                                        create_track_callback(self._stop_listen, prop, include_track_id=True))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/track/set/%s" % prop,
                                        create_track_callback(self._set_property, prop))

        #--------------------------------------------------------------------------------
        # Volume, panning and send are properties of the track's mixer_device so
        # can't be formulated as normal callbacks that reference properties of track.
        #--------------------------------------------------------------------------------
        mixer_properties_rw: List[str] = ["volume", "panning"]
        for prop in mixer_properties_rw:
            self.osc_server.add_handler("/live/track/get/%s" % prop,
                                        create_track_callback(self._get_mixer_property, prop))
            self.osc_server.add_handler("/live/track/set/%s" % prop,
                                        create_track_callback(self._set_mixer_property, prop))
            self.osc_server.add_handler("/live/track/start_listen/%s" % prop,
                                        create_track_callback(self._start_mixer_listen, prop, include_track_id=True))
            self.osc_server.add_handler("/live/track/stop_listen/%s" % prop,
                                        create_track_callback(self._stop_mixer_listen, prop, include_track_id=True))

        def track_get_send(track: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            send_id, = params
            return send_id, track.mixer_device.sends[send_id].value

        def track_set_send(track: Any, params: Tuple[Any, ...] = ()) -> None:
            send_id, value = params
            track.mixer_device.sends[send_id].value = value

        self.osc_server.add_handler("/live/track/get/send", create_track_callback(track_get_send))
        self.osc_server.add_handler("/live/track/set/send", create_track_callback(track_set_send))

        def track_delete_clip(track: Any, params: Tuple[Any, ...]) -> None:
            clip_index, = params
            track.clip_slots[clip_index].delete_clip()

        self.osc_server.add_handler("/live/track/delete_clip", create_track_callback(track_delete_clip))

        def track_create_audio_clip(track: Any, params: Tuple[Any, ...]) -> Tuple[Any, ...]:
            """
            Create an audio clip in the arrangement view at a specific beat
            position. Signature: (track_index, file_path, position_beats).

            The file_path must already exist on disk — Live cannot fetch from
            URLs and applies project-folder constraints on what it will read.
            Callers are expected to materialize the audio into the current
            Live project's samples folder before invoking this handler.

            Returns (clip_index, status) where clip_index is the position in
            track.arrangement_clips of the newly created clip, or -1 on
            failure. Status is one of: "ok", "missing", "not_supported",
            "error".
            """
            if len(params) < 2:
                self.logger.error("create_audio_clip: requires (file_path, position_beats)")
                return (-1, "error")
            file_path: str = str(params[0])
            position: float = float(params[1])
            abs_path: str = os.path.abspath(file_path)
            if not os.path.exists(abs_path):
                self.logger.error("create_audio_clip: file not found: %s" % abs_path)
                return (-1, "missing")
            if not hasattr(track, "create_audio_clip"):
                # Track.create_audio_clip ships with Live 12.0.5+. Older
                # versions need a Browser-walk + load-into-slot dance instead,
                # which is session-view only — the arrangement surface has no
                # equivalent fallback, so fail loudly rather than silently.
                self.logger.error(
                    "create_audio_clip: Live does not expose Track.create_audio_clip "
                    "(requires Live 12.0.5+)"
                )
                return (-1, "not_supported")
            # Bracket the LOM call with log lines so a client-side timeout
            # can be triaged from Live's Log.txt: if "invoking" lands but
            # "returned" does not, the LOM call itself is blocking Live's
            # main thread (decode, warp analysis, project-folder dialog,
            # etc.) and no OSC reply will ship until it unblocks. Without
            # these we can only see "client timed out" with no breadcrumb.
            self.logger.info(
                "create_audio_clip: invoking track.create_audio_clip(%r, %f) "
                "on track %r" % (abs_path, position, getattr(track, "name", "?"))
            )
            try:
                new_clip: Any = track.create_audio_clip(abs_path, position)
            except Exception as e:
                self.logger.error("create_audio_clip: Live raised: %s" % e)
                return (-1, "error")
            self.logger.info(
                "create_audio_clip: LOM returned; resolving clip index for %r" % abs_path
            )

            # Resolve the new clip's arrangement_clips index. Identity match
            # is the canonical lookup; if Live ever returns a wrapper that
            # doesn't compare `is` with the live tuple entry, fall back to
            # start_time. Position collisions on the same track are possible
            # but rare; the identity path covers the common case.
            clip_index: int = -1
            arrangement_clips: Any = track.arrangement_clips
            for i in range(len(arrangement_clips)):
                if arrangement_clips[i] is new_clip:
                    clip_index = i
                    break
            if clip_index == -1:
                for i in range(len(arrangement_clips)):
                    if abs(arrangement_clips[i].start_time - position) < 1e-6:
                        clip_index = i
                        break
            if clip_index == -1:
                # Live's `create_audio_clip` returned without raising, but
                # neither the identity walk nor the start_time fallback
                # could resolve the new clip inside `track.arrangement_clips`.
                # Returning ("ok", -1) would lie to the client — every
                # downstream OSC address keys off the clip index, so a -1
                # corrupts the next message. Surface as an error instead so
                # the Electron side raises and the user sees the failure.
                self.logger.error(
                    "create_audio_clip: LOM returned but clip not found in "
                    "arrangement_clips for path=%r position=%f" % (abs_path, position)
                )
                return (-1, "clip_not_found")
            return (clip_index, "ok")

        self.osc_server.add_handler(
            "/live/track/create_audio_clip", create_track_callback(track_create_audio_clip)
        )

        def track_get_clip_names(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(clip_slot.clip.name if clip_slot.clip else None for clip_slot in track.clip_slots)

        def track_get_clip_lengths(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(clip_slot.clip.length if clip_slot.clip else None for clip_slot in track.clip_slots)

        def track_get_clip_colors(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(clip_slot.clip.color if clip_slot.clip else None for clip_slot in track.clip_slots)

        def track_get_arrangement_clip_names(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(clip.name for clip in track.arrangement_clips)

        def track_get_arrangement_clip_lengths(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(clip.length for clip in track.arrangement_clips)

        def track_get_arrangement_clip_start_times(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(clip.start_time for clip in track.arrangement_clips)

        """
        Returns a list of clip properties, or Nil if clip is empty
        """
        self.osc_server.add_handler("/live/track/get/clips/name", create_track_callback(track_get_clip_names))
        self.osc_server.add_handler("/live/track/get/clips/length", create_track_callback(track_get_clip_lengths))
        self.osc_server.add_handler("/live/track/get/clips/color", create_track_callback(track_get_clip_colors))
        self.osc_server.add_handler("/live/track/get/arrangement_clips/name", create_track_callback(track_get_arrangement_clip_names))
        self.osc_server.add_handler("/live/track/get/arrangement_clips/length", create_track_callback(track_get_arrangement_clip_lengths))
        self.osc_server.add_handler("/live/track/get/arrangement_clips/start_time", create_track_callback(track_get_arrangement_clip_start_times))

        def track_duplicate_clip_to_arrangement(track: Any, params: Tuple[Any, ...]) -> Tuple[Any, ...]:
            # Live's Track.duplicate_clip_to_arrangement(clip, position) copies a
            # clip into the arrangement at `position` (beats from arrangement
            # start). The second argument is the Clip itself (`clip_slot.clip`),
            # NOT the ClipSlot — passing the slot raises:
            #   "Python argument types ... did not match C++ signature
            #    duplicate_clip_to_arrangement(self, TPyHandle<AClip> clip,
            #    double destination_time)"
            # This is the only Live API path that inserts a clip into the
            # arrangement programmatically — there is no
            # `clip_slot.create_arrangement_clip()` and
            # `clip_slot.duplicate_clip_to()` only moves between session slots.
            #
            # Reply: (clip_index, position, status). Empty-slot and Live API
            # failures surface as status strings, mirroring browser.load_file.
            #
            # Optional loop brace: params (loop_start, loop_end) in beats. When
            # both are present the duplicated arrangement clip is set to loop
            # over [loop_start, loop_end]. The clip's timeline length was framed
            # by the source slot clip's start/end markers (set by the caller
            # before this call), so enabling looping tiles the brace across that
            # existing length rather than resizing the clip. Omitted (2-arg
            # call) -> one-shot placement.
            clip_index: int = int(params[0])
            position: float = float(params[1])
            loop_start: Optional[float] = float(params[2]) if len(params) >= 4 else None
            loop_end: Optional[float] = float(params[3]) if len(params) >= 4 else None
            try:
                clip_slot: Any = track.clip_slots[clip_index]
            except IndexError:
                return (clip_index, position, "no_slot")
            if not clip_slot.has_clip:
                self.logger.error("Slot %d on track has no clip to duplicate" % clip_index)
                return (clip_index, position, "no_clip")
            clip: Any = clip_slot.clip
            if clip is None:
                # has_clip true but .clip None — race during clip teardown;
                # treat as no_clip so the client can retry or surface the gap.
                self.logger.error("Slot %d has_clip=True but .clip is None" % clip_index)
                return (clip_index, position, "no_clip")
            try:
                new_clip: Any = track.duplicate_clip_to_arrangement(clip, position)
            except Exception as e:
                self.logger.error("duplicate_clip_to_arrangement failed: %s" % e)
                self.osc_server.send("/live/error", ("duplicate_clip_to_arrangement failed: %s" % e,))
                return (clip_index, position, "duplicate_failed")

            if loop_start is not None and loop_end is not None:
                # `duplicate_clip_to_arrangement` returns the new arrangement
                # Clip directly. Identity is exact; the start_time scan is a
                # fallback for Live builds that return None. The placement
                # already succeeded, so a resolution miss logs loudly but still
                # reports "ok" — the clip is in the arrangement, only the loop
                # brace went unset.
                arr_clip: Any = new_clip
                if arr_clip is None:
                    for candidate in track.arrangement_clips:
                        if abs(candidate.start_time - position) < 1e-6:
                            arr_clip = candidate
                            break
                if arr_clip is None:
                    self.logger.error(
                        "duplicate_clip_to_arrangement: clip placed at %f but "
                        "could not be resolved to set loop brace" % position
                    )
                    return (clip_index, position, "ok")
                # Enable looping first, then set loop_end before loop_start so
                # the loop_start < loop_end invariant holds at each step (the
                # brace starts at the inherited markers, which sit at or after
                # the new loop region).
                arr_clip.looping = True
                arr_clip.loop_end = loop_end
                arr_clip.loop_start = loop_start

            return (clip_index, position, "ok")

        self.osc_server.add_handler("/live/track/duplicate_clip_to_arrangement",
                                    create_track_callback(track_duplicate_clip_to_arrangement))

        def track_get_num_devices(track: Any, _: Any) -> Tuple[Any, ...]:
            return len(track.devices),

        def track_get_device_names(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(device.name for device in track.devices)

        def track_get_device_types(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(device.type for device in track.devices)

        def track_get_device_class_names(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(device.class_name for device in track.devices)

        def track_get_device_can_have_chains(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple(device.can_have_chains for device in track.devices)

        """
         - name: the device's human-readable name
         - type: 0 = audio_effect, 1 = instrument, 2 = midi_effect
         - class_name: e.g. Operator, Reverb, AuPluginDevice, PluginDevice, InstrumentGroupDevice
        """
        self.osc_server.add_handler("/live/track/get/num_devices", create_track_callback(track_get_num_devices))
        self.osc_server.add_handler("/live/track/get/devices/name", create_track_callback(track_get_device_names))
        self.osc_server.add_handler("/live/track/get/devices/type", create_track_callback(track_get_device_types))
        self.osc_server.add_handler("/live/track/get/devices/class_name", create_track_callback(track_get_device_class_names))
        self.osc_server.add_handler("/live/track/get/devices/can_have_chains", create_track_callback(track_get_device_can_have_chains))

        #--------------------------------------------------------------------------------
        # Track: Output routing.
        # An output route has a type (e.g. "Ext. Out") and a channel (e.g. "1/2").
        # Since Live 10, both of these need to be set by reference to the appropriate
        # item in the available_output_routing_types vector.
        #--------------------------------------------------------------------------------
        def track_get_available_output_routing_types(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple([routing_type.display_name for routing_type in track.available_output_routing_types])
        def track_get_available_output_routing_channels(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple([routing_channel.display_name for routing_channel in track.available_output_routing_channels])
        def track_get_output_routing_type(track: Any, _: Any) -> Tuple[Any, ...]:
            return track.output_routing_type.display_name,
        def track_set_output_routing_type(track: Any, params: Tuple[Any, ...]) -> None:
            type_name: str = str(params[0])
            for routing_type in track.available_output_routing_types:
                if routing_type.display_name == type_name:
                    track.output_routing_type = routing_type
                    return
            self.logger.warning("Couldn't find output routing type: %s" % type_name)
        def track_get_output_routing_channel(track: Any, _: Any) -> Tuple[Any, ...]:
            return track.output_routing_channel.display_name,
        def track_set_output_routing_channel(track: Any, params: Tuple[Any, ...]) -> None:
            channel_name: str = str(params[0])
            for channel in track.available_output_routing_channels:
                if channel.display_name == channel_name:
                    track.output_routing_channel = channel
                    return
            self.logger.warning("Couldn't find output routing channel: %s" % channel_name)

        self.osc_server.add_handler("/live/track/get/available_output_routing_types", create_track_callback(track_get_available_output_routing_types))
        self.osc_server.add_handler("/live/track/get/available_output_routing_channels", create_track_callback(track_get_available_output_routing_channels))
        self.osc_server.add_handler("/live/track/get/output_routing_type", create_track_callback(track_get_output_routing_type))
        self.osc_server.add_handler("/live/track/set/output_routing_type", create_track_callback(track_set_output_routing_type))
        self.osc_server.add_handler("/live/track/get/output_routing_channel", create_track_callback(track_get_output_routing_channel))
        self.osc_server.add_handler("/live/track/set/output_routing_channel", create_track_callback(track_set_output_routing_channel))

        #--------------------------------------------------------------------------------
        # Track: Input routing.
        #--------------------------------------------------------------------------------
        def track_get_available_input_routing_types(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple([routing_type.display_name for routing_type in track.available_input_routing_types])
        def track_get_available_input_routing_channels(track: Any, _: Any) -> Tuple[Any, ...]:
            return tuple([routing_channel.display_name for routing_channel in track.available_input_routing_channels])
        def track_get_input_routing_type(track: Any, _: Any) -> Tuple[Any, ...]:
            return track.input_routing_type.display_name,
        def track_set_input_routing_type(track: Any, params: Tuple[Any, ...]) -> None:
            type_name: str = str(params[0])
            for routing_type in track.available_input_routing_types:
                if routing_type.display_name == type_name:
                    track.input_routing_type = routing_type
                    return
            self.logger.warning("Couldn't find input routing type: %s" % type_name)
        def track_get_input_routing_channel(track: Any, _: Any) -> Tuple[Any, ...]:
            return track.input_routing_channel.display_name,
        def track_set_input_routing_channel(track: Any, params: Tuple[Any, ...]) -> None:
            channel_name: str = str(params[0])
            for channel in track.available_input_routing_channels:
                if channel.display_name == channel_name:
                    track.input_routing_channel = channel
                    return
            self.logger.warning("Couldn't find input routing channel: %s" % channel_name)

        self.osc_server.add_handler("/live/track/get/available_input_routing_types", create_track_callback(track_get_available_input_routing_types))
        self.osc_server.add_handler("/live/track/get/available_input_routing_channels", create_track_callback(track_get_available_input_routing_channels))
        self.osc_server.add_handler("/live/track/get/input_routing_type", create_track_callback(track_get_input_routing_type))
        self.osc_server.add_handler("/live/track/set/input_routing_type", create_track_callback(track_set_input_routing_type))
        self.osc_server.add_handler("/live/track/get/input_routing_channel", create_track_callback(track_get_input_routing_channel))
        self.osc_server.add_handler("/live/track/set/input_routing_channel", create_track_callback(track_set_input_routing_channel))

    def _set_mixer_property(self, target: Any, prop: str, params: Tuple[Any, ...]) -> None:
        parameter_object: Any = getattr(target.mixer_device, prop)
        self.logger.info("Setting property for %s: %s (new value %s)" % (self.class_identifier, prop, params[0]))
        parameter_object.value = params[0]

    def _get_mixer_property(self, target: Any, prop: str, params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
        parameter_object: Any = getattr(target.mixer_device, prop)
        self.logger.info("Getting property for %s: %s = %s" % (self.class_identifier, prop, parameter_object.value))
        return parameter_object.value,

    def _start_mixer_listen(self, target: Any, prop: str, params: Optional[Tuple[Any, ...]] = ()) -> None:
        parameter_object: Any = getattr(target.mixer_device, prop)
        def property_changed_callback() -> None:
            value: Any = parameter_object.value
            self.logger.info("Property %s changed of %s %s: %s" % (prop, self.class_identifier, str(params), value))
            osc_address: str = "/live/%s/get/%s" % (self.class_identifier, prop)
            self.osc_server.send(osc_address, (*params, value,))

        listener_key: Tuple[Any, ...] = (prop, tuple(params))
        if listener_key in self.listener_functions:
            self._stop_mixer_listen(target, prop, params)

        self.logger.info("Adding listener for %s %s, property: %s" % (self.class_identifier, str(params), prop))

        parameter_object.add_value_listener(property_changed_callback)
        self.listener_functions[listener_key] = property_changed_callback
        self.listener_objects[listener_key] = target
        # Mixer listeners live on `target.mixer_device.<prop>` (a DeviceParameter),
        # not on the Track itself, so the generic `target.remove_<prop>_listener`
        # lookup in _stop_listen would AttributeError. Register the actual
        # remover so _clear_listeners cleans up correctly during reload.
        self.listener_removers[listener_key] = lambda po=parameter_object, fn=property_changed_callback: po.remove_value_listener(fn)
        #--------------------------------------------------------------------------------
        # Immediately send the current value
        #--------------------------------------------------------------------------------
        property_changed_callback()

    def _stop_mixer_listen(self, target: Any, prop: str, params: Optional[Tuple[Any, ...]] = ()) -> None:
        listener_key: Tuple[Any, ...] = (prop, tuple(params))
        if listener_key in self.listener_functions:
            self.logger.info("Removing listener for %s %s, property %s" % (self.class_identifier, str(params), prop))
            listener_function: Callable[[], None] = self.listener_functions[listener_key]
            #--------------------------------------------------------------------------------
            # Prefer the remover registered at listener-start: it captures the
            # DeviceParameter the listener is actually attached to. Re-resolving
            # `target.mixer_device.<prop>` here would target whichever track
            # currently sits at the index — the wrong parameter after tracks
            # are deleted or reordered.
            #--------------------------------------------------------------------------------
            remover: Optional[Callable[[], None]] = self.listener_removers.get(listener_key)
            try:
                if remover is not None:
                    remover()
                else:
                    getattr(target.mixer_device, prop).remove_value_listener(listener_function)
            except Exception as e:
                #--------------------------------------------------------------------------------
                # Benign when the observed DeviceParameter is gone (its track
                # deleted). Fall through and drop registry state so the key
                # stays usable for future start_listen calls.
                #--------------------------------------------------------------------------------
                self.logger.info("Exception whilst removing mixer listener (likely benign): %s" % e)

            self.listener_functions.pop(listener_key, None)
            self.listener_objects.pop(listener_key, None)
            self.listener_removers.pop(listener_key, None)
        else:
            self.logger.warning("No listener function found for property: %s (%s)" % (prop, str(params)))
