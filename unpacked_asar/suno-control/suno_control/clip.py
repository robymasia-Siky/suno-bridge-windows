from __future__ import annotations

import re
from typing import Tuple, Callable, Any, Optional, List
from .handler import AbletonOSCHandler
import Live

def note_name_to_midi(name: str) -> Optional[int]:
    """ Maps a MIDI note name (D3, C#6) to a value.
    Assumes that middle C is C4. """
    note_names: List[List[str]] = [["C"],
                  ["C#", "Db"],
                  ["D"],
                  ["D#", "Eb"],
                  ["E"],
                  ["F"],
                  ["F#", "Gb"],
                  ["G"],
                  ["G#", "Ab"],
                  ["A"],
                  ["A#", "Bb"],
                  ["B"]]

    for index, names in enumerate(note_names):
        if name in names:
            return index
    return None

class ClipHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "clip"
        self._clip_notes_cache: List[Any] = []

    def init_api(self) -> None:
        def create_clip_callback(func: Callable[..., Any], *args: Any, pass_clip_index: bool = False, arrangement: bool = False) -> Callable[[Tuple[Any, ...]], Optional[Tuple[Any, ...]]]:
            """
            Creates a callback that expects the following set of arguments:
              (track_index, clip_index, *args)

            The callback then extracts the relevant `Clip` object from the current Song,
            and calls `func` with this `Clip` object plus any additional *args.

            pass_clip_index is a bit of an ugly hack, although seems like the lesser of
            evils for scenarios where the track/clip index is needed (as a clip is unable
            to query its own index). Other alternatives include _always_ passing track/clip
            index to the callback, but this adds arg clutter to every single callback.
            """

            def clip_callback(params: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
                #--------------------------------------------------------------------------------
                # Cast to int to support clients such as TouchOSC that, by default, pass all
                # numeric arguments as float.
                #--------------------------------------------------------------------------------
                track_index: int = int(params[0])
                clip_index: int = int(params[1])
                track: Any = self.song.tracks[track_index]
                clip: Any = track.arrangement_clips[clip_index] if arrangement else track.clip_slots[clip_index].clip
                if pass_clip_index:
                    rv: Any = func(clip, *args, tuple(params[0:]))
                else:
                    rv = func(clip, *args, tuple(params[2:]))

                if rv is not None:
                    return (track_index, clip_index, *rv)
                return None

            return clip_callback

        methods: List[str] = [
            "fire",
            "stop",
            "duplicate_loop",
            "remove_notes_by_id"
        ]
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
            "will_record_on_start"
            ## TODO list:
            ##"groove", ## if other than None, says "Error handling OSC message: Infered arg_value type is not supported"
            ## is_arrangement_clip
            ## "warp_markers" is NOT here on purpose: the generic property
            ## plumbing only speaks OSC scalars, and Live returns a vector of
            ## WarpMarker objects ("Infered arg_value type is not supported").
            ## Warp markers go through the dedicated flattened-pair handlers
            ## /live/clip/get/warp_markers + /live/clip/set/warp_markers below.
            ##"view", ##"Infered arg_value type is not supported"
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

        for method in methods:
            self.osc_server.add_handler("/live/clip/%s" % method,
                                        create_clip_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/clip/get/%s" % prop,
                                        create_clip_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/clip/start_listen/%s" % prop,
                                        create_clip_callback(self._start_listen, prop, pass_clip_index=True))
            self.osc_server.add_handler("/live/clip/stop_listen/%s" % prop,
                                        create_clip_callback(self._stop_listen, prop, pass_clip_index=True))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/clip/set/%s" % prop,
                                        create_clip_callback(self._set_property, prop))

        def clip_get_notes(clip: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            if len(params) == 4:
                pitch_start, pitch_span, time_start, time_span = params
            elif len(params) == 0:
                pitch_start, pitch_span, time_start, time_span = 0, 127, -8192, 16384
            else:
                raise ValueError("Invalid number of arguments for /clip/get/notes. Either 0 or 4 arguments must be passed.")
            notes: Any = clip.get_notes_extended(pitch_start, pitch_span, time_start, time_span)
            all_note_attributes: List[Any] = []
            for note in notes:
                all_note_attributes += [note.pitch, note.start_time, note.duration, note.velocity, note.mute]
            return tuple(all_note_attributes)

        def clip_add_notes(clip: Any, params: Tuple[Any, ...] = ()) -> None:
            notes: List[Any] = []
            for offset in range(0, len(params), 5):
                pitch, start_time, duration, velocity, mute = params[offset:offset + 5]
                note: Any = Live.Clip.MidiNoteSpecification(start_time=start_time,
                                                       duration=duration,
                                                       pitch=pitch,
                                                       velocity=velocity,
                                                       mute=mute)
                notes.append(note)
            clip.add_new_notes(tuple(notes))

        def clip_remove_notes(clip: Any, params: Tuple[Any, ...] = ()) -> None:
            if len(params) == 4:
                pitch_start, pitch_span, time_start, time_span = params
            elif len(params) == 0:
                pitch_start, pitch_span, time_start, time_span = 0, 127, -8192, 16384
            else:
                raise ValueError("Invalid number of arguments for /clip/remove/notes. Either 0 or 4 arguments must be passed.")
            clip.remove_notes_extended(pitch_start, pitch_span, time_start, time_span)

        self.osc_server.add_handler("/live/clip/get/notes", create_clip_callback(clip_get_notes))
        self.osc_server.add_handler("/live/clip/add/notes", create_clip_callback(clip_add_notes))
        self.osc_server.add_handler("/live/clip/remove/notes", create_clip_callback(clip_remove_notes))

        #--------------------------------------------------------------------------------
        # Warp markers.
        #
        # The generic property plumbing can't carry these (Live returns a vector
        # of WarpMarker objects, and pythonosc only encodes scalars), so — like
        # the MIDI-note handlers above — markers cross the wire as FLATTENED
        # FLOAT PAIRS: (beat_time, sample_time, beat_time, sample_time, ...).
        # beat_time is the clip content-beat, sample_time is seconds into the
        # source audio file — the two fields of Live.Clip.WarpMarker.
        #
        # NOTE: the Max-for-Live LOM documents add_warp_marker as taking a
        # dict, but the Remote Script API has no dict→TWarpMarker converter
        # ("No registered converter was able to produce a C++ rvalue of type
        # NApiHelpers::TWarpMarker") — adds MUST pass a
        # Live.Clip.WarpMarker(sample_time, beat_time) object.
        #--------------------------------------------------------------------------------

        # Match tolerances when comparing Live's markers with the requested
        # set. Wire floats are 32-bit (~7 significant digits), so a value in
        # the hundreds can arrive up to ~1e-4 off; 1e-3 beats (about 0.5 ms at
        # 120 BPM) / 1e-3 seconds is far below marker-placement resolution.
        # A marker only counts as matching when BOTH dimensions agree — an
        # auto-warp marker at the right beat but the wrong sample position is
        # a different tempo map and must be replaced, not kept.
        WARP_MARKER_BEAT_EPSILON: float = 1e-3
        WARP_MARKER_SAMPLE_EPSILON: float = 1e-3

        def warp_marker_pairs(clip: Any) -> List[Tuple[float, float]]:
            return [
                (float(marker.beat_time), float(marker.sample_time))
                for marker in clip.warp_markers
            ]

        def has_marker(pairs: List[Tuple[float, float]],
                       beat_time: float, sample_time: float) -> bool:
            return any(
                abs(beat - beat_time) < WARP_MARKER_BEAT_EPSILON
                and abs(sample - sample_time) < WARP_MARKER_SAMPLE_EPSILON
                for beat, sample in pairs)

        def clip_get_warp_markers(clip: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            pairs: List[float] = []
            for beat_time, sample_time in warp_marker_pairs(clip):
                pairs += [beat_time, sample_time]
            return (len(pairs) // 2, *pairs)

        def beat_at_sample(markers: List[Tuple[float, float]], sample_time: float) -> float:
            """
            The requested map's beat time at `sample_time`: linear interpolation
            on the bracketing segment, end-segment extrapolation outside the
            marker span — the same rule Live applies when playing the map.
            `markers` is (beat, sample) pairs sorted ascending in both fields.
            """
            if sample_time <= markers[0][1]:
                (b0, s0), (b1, s1) = markers[0], markers[1]
            elif sample_time >= markers[-1][1]:
                (b0, s0), (b1, s1) = markers[-2], markers[-1]
            else:
                (b0, s0), (b1, s1) = markers[0], markers[1]
                for i in range(1, len(markers)):
                    if markers[i][1] >= sample_time:
                        (b0, s0), (b1, s1) = markers[i - 1], markers[i]
                        break
            if s1 == s0:
                return b0
            return b0 + (b1 - b0) * (sample_time - s0) / (s1 - s0)

        def clamp_markers_to_sample(clip: Any,
                                    desired: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
            """
            Project markers outside the clip sample's range onto its boundary.

            Live rejects add_warp_marker when sample_time falls outside
            [0, sample length] — and a rejected endpoint leaves a partial map
            (often a single marker), degenerating the clip back to Live's own
            auto-warp tempo line, which the sender's beat-domain trims did NOT
            assume. Studio maps can legitimately overshoot the file (the map
            spans the song's full beat grid; the staged audio may be shorter),
            so out-of-range markers are replaced with a boundary marker on the
            SAME tempo line (beat interpolated at sample 0 / sample end) —
            playback within the audible range is identical.

            Falls back to the untouched set when the clip doesn't expose
            sample_length/sample_rate (MIDI clip, older Live API).
            """
            try:
                duration = float(clip.sample_length) / float(clip.sample_rate)
            except Exception:
                return desired
            if not (duration > 0):
                return desired
            if all(0.0 <= sample <= duration for _, sample in desired):
                return desired
            # The upper boundary sits a hair inside the sample end: our
            # duration comes from a float division of sample_length by
            # sample_rate, and a rounding disagreement with Live's own range
            # check would re-trigger the rejection this clamp exists to avoid.
            # Any point ON the tempo line preserves it, so the margin is free.
            upper = duration - 1e-3
            if upper <= WARP_MARKER_SAMPLE_EPSILON:
                # Sub-millisecond sample: the two boundary anchors would
                # coincide; nothing meaningful can be clamped.
                return desired

            def has_sample(pairs: List[Tuple[float, float]], sample_time: float) -> bool:
                return any(abs(sample - sample_time) < WARP_MARKER_SAMPLE_EPSILON
                           for _, sample in pairs)

            clamped = [(beat, sample) for beat, sample in desired
                       if 0.0 <= sample <= duration]
            if any(sample < 0.0 for _, sample in desired) and not has_sample(clamped, 0.0):
                clamped.append((beat_at_sample(desired, 0.0), 0.0))
            if any(sample > duration for _, sample in desired) and not has_sample(clamped, upper):
                clamped.append((beat_at_sample(desired, upper), upper))
            # A one-sided overshoot can still leave a single anchor (e.g.
            # every marker below zero collapses onto sample 0). A tempo line
            # needs two: anchor the missing boundary on the same
            # (extrapolated) line rather than falling back to a set Live
            # would reject.
            if len(clamped) < 2:
                if not has_sample(clamped, 0.0):
                    clamped.append((beat_at_sample(desired, 0.0), 0.0))
                if len(clamped) < 2 and not has_sample(clamped, upper):
                    clamped.append((beat_at_sample(desired, upper), upper))
            clamped.sort()
            self.logger.info(
                "set_warp_markers: clamped %d marker(s) outside the sample range "
                "[0, %s] onto its boundary (same tempo line)",
                len(desired) - sum(1 for _, s in desired if 0.0 <= s <= duration),
                duration)
            return clamped

        def clip_set_warp_markers(clip: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            """
            Replace the clip's warp markers with the requested set.

            Args: flattened (beat_time, sample_time) float pairs. Requires a
            WARPED audio clip (Live's add_warp_marker is only available then —
            the caller writes /live/clip/set/warping true first, and Live
            processes one sender's packets in order).

            Markers whose sample_time falls outside the clip sample's range
            are projected onto its boundary on the same tempo line first
            (see clamp_markers_to_sample) — Live rejects them outright, and a
            rejected endpoint would leave a partial, mis-timed map.

            Live has no bulk-set API, so this converges add/prune-wise:
              1. add every requested marker not already present,
              2. remove every existing marker not in the requested set,
              3. repeat — an add can fail while a stale neighbor constrains it
                 (sample_time must stay monotonic between adjacent markers,
                 segment BPM must stay within [5, 999]), and succeed once the
                 prune clears that neighbor.
            Individual add/remove failures are tolerated per marker; the reply
            reports how many requested markers actually landed:
              (status, requested_count, applied_count)
            with status "ok" when every marker landed, else "partial".
            """
            if len(params) % 2 != 0:
                raise ValueError(
                    "/live/clip/set/warp_markers expects flattened "
                    "(beat_time, sample_time) float pairs; got %d args" % len(params))
            desired: List[Tuple[float, float]] = sorted(
                (float(params[i]), float(params[i + 1])) for i in range(0, len(params), 2))
            if len(desired) < 2:
                # <2 markers can't define a tempo map (Live itself keeps a
                # hidden end marker for the final segment's BPM); rejecting
                # here mirrors Studio's own >=2 rule (areWarpMarkersPopulated).
                raise ValueError(
                    "/live/clip/set/warp_markers needs at least 2 markers; got %d" % len(desired))
            if not clip.warping:
                raise RuntimeError(
                    "add_warp_marker requires a warped clip; set /live/clip/set/warping true first")
            desired = clamp_markers_to_sample(clip, desired)

            # Two passes cover most constraint shapes (add what fits, prune
            # the stale set, then add what the prune unblocked); an auto-warp
            # marker at a desired beat but the wrong sample position takes a
            # third (its add fails as a duplicate beat until the prune clears
            # it). The loop exits early once a pass changes nothing.
            for _pass in range(3):
                changed = False
                current = warp_marker_pairs(clip)
                for beat_time, sample_time in desired:
                    if has_marker(current, beat_time, sample_time):
                        continue
                    try:
                        # WarpMarker's constructor order is (sample_time, beat_time)
                        # — Live 12 API stubs; a dict here is NOT converted.
                        clip.add_warp_marker(Live.Clip.WarpMarker(sample_time, beat_time))
                        changed = True
                    except Exception as exc:
                        self.logger.info(
                            "add_warp_marker(beat=%s, sample=%s) failed (pass %d): %s",
                            beat_time, sample_time, _pass, exc)
                for beat_time, sample_time in warp_marker_pairs(clip):
                    if has_marker(desired, beat_time, sample_time):
                        continue
                    try:
                        clip.remove_warp_marker(beat_time)
                        changed = True
                    except Exception as exc:
                        # Live's hidden last marker (the final segment's BPM
                        # anchor) can refuse removal — benign, leave it.
                        self.logger.info(
                            "remove_warp_marker(beat=%s) failed (pass %d): %s",
                            beat_time, _pass, exc)
                if not changed:
                    break

            final = warp_marker_pairs(clip)
            applied = sum(
                1 for beat, sample in desired if has_marker(final, beat, sample))
            status = "ok" if applied == len(desired) else "partial"
            self.logger.info(
                "set_warp_markers: %s (%d/%d markers applied, clip now has %d)",
                status, applied, len(desired), len(final))
            return (status, len(desired), applied)

        self.osc_server.add_handler("/live/clip/get/warp_markers",
                                    create_clip_callback(clip_get_warp_markers))
        self.osc_server.add_handler("/live/clip/set/warp_markers",
                                    create_clip_callback(clip_set_warp_markers))
        self.osc_server.add_handler(
            "/live/arrangement_clip/get/warp_markers",
            create_clip_callback(clip_get_warp_markers, arrangement=True),
        )
        self.osc_server.add_handler(
            "/live/arrangement_clip/set/warp_markers",
            create_clip_callback(clip_set_warp_markers, arrangement=True),
        )

        def clips_filter_handler(params: Tuple[Any, ...]) -> None:
            # TODO: Pre-cache clip notes
            if len(self._clip_notes_cache) == 0:
                self.logger.warning("Building clip notes cache...")
                self._build_clip_name_cache()
            else:
                self.logger.warning("Found existing clip notes cache (len = %d)" % len(self._clip_notes_cache))
            note_indices: List[Optional[int]] = [note_name_to_midi(name) for name in params]

            self.logger.warning("Got note indices: %s" % note_indices)
            for track_index, track in enumerate(self.song.tracks):
                for clip_slot_index, clip_slot in enumerate(track.clip_slots):
                    clip_notes_list: Any = self._clip_notes_cache[track_index][clip_slot_index]
                    if clip_notes_list:
                        clip: Any = clip_slot.clip
                        if all(note in note_indices for note in clip_notes_list):
                            clip.muted = False
                        else:
                            clip.muted = True

        self.osc_server.add_handler("/live/clips/filter", clips_filter_handler)

        def clips_unfilter_handler(params: Tuple[Any, ...]) -> None:
            track_start: int = params[0] if len(params) > 0 else 0
            track_end: int = params[1] if len(params) > 1 else len(self.song.tracks)

            self.logger.info("Unfiltering tracks: %d .. %d" % (track_start, track_end))
            for track in self.song.tracks[track_start:track_end]:
                for clip_slot in track.clip_slots:
                    if clip_slot.has_clip:
                        clip = clip_slot.clip
                        clip.muted = False

        self.osc_server.add_handler("/live/clips/unfilter", clips_unfilter_handler)

    def _build_clip_name_cache(self) -> None:
        regex: str = "([_-])([A-G][A-G#b1-9-]*)$"
        for track_index, track in enumerate(self.song.tracks):
            self._clip_notes_cache.append([])
            for clip_slot_index, clip_slot in enumerate(track.clip_slots):
                self._clip_notes_cache[-1].append([])
                if clip_slot.has_clip:
                    clip: Any = clip_slot.clip
                    clip_name: str = clip.name
                    match = re.search(regex, clip_name)
                    if match:
                        clip_notes_str: str = match.group(2)
                        clip_notes_str = re.sub("[1-9]", "", clip_notes_str)
                        clip_notes_list: List[str] = clip_notes_str.split("-")
                        clip_notes_midi: List[Optional[int]] = [note_name_to_midi(name) for name in clip_notes_list]
                        self._clip_notes_cache[-1][-1] = clip_notes_midi
