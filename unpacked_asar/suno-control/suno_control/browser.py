"""
Load audio into clip slots through Live's Browser or a direct file path.

    /live/clip_slot/load_file   (track, clip, path, direct=False)

Create requests direct loading with ClipSlot.create_audio_clip so newly
downloaded audio does not need to appear in Live's Browser first. Other
callers use the cached Browser walk and load_item.

If the file isn't reachable through the Browser's existing roots, callers can
add its parent directory as a User Folder via:

    /live/browser/add_user_folder  (folder_path)
"""
from __future__ import annotations

import os
import Live
from typing import Tuple, Any, Optional, Dict, List

from .handler import AbletonOSCHandler


class BrowserHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "browser"
        self._uri_cache: Dict[str, Any] = {}

    def init_api(self) -> None:
        self.osc_server.add_handler("/live/clip_slot/load_file", self._load_file_into_slot)
        self.osc_server.add_handler("/live/browser/load_file", self._load_file_into_selected_slot)
        self.osc_server.add_handler("/live/browser/get/roots", self._get_roots)
        self.osc_server.add_handler("/live/browser/clear_cache", self._clear_cache)
        self.osc_server.add_handler("/live/browser/add_user_folder", self._add_user_folder)

    def _browser(self) -> Any:
        return Live.Application.get_application().browser

    def _roots(self) -> List[Tuple[str, Any]]:
        b: Any = self._browser()
        candidates: List[str] = [
            "user_folders", "user_library", "current_project", "packs",
            "samples", "audio_clips", "sounds", "drums", "instruments",
            "audio_effects", "midi_effects", "max_for_live", "plugins",
        ]
        roots: List[Tuple[str, Any]] = []
        for name in candidates:
            try:
                root: Any = getattr(b, name, None)
                if root is not None:
                    roots.append((name, root))
            except Exception as e:
                self.logger.debug("Browser root '%s' not accessible: %s" % (name, e))
        return roots

    def _get_roots(self, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
        return tuple(name for name, _ in self._roots())

    def _children_of(self, node: Any) -> List[Any]:
        """
        Live exposes two shapes for "things that hold child BrowserItems":

        - A `BrowserItem` (e.g. `browser.user_library`) carries a `.children`
          tuple of child BrowserItems.
        - A `BrowserItemVector` (e.g. `browser.user_folders`) IS the sequence
          of root items directly — iterable, but `.children` is absent and
          touching it raises `'BrowserItemVector' object has no attribute
          'children'`. Each element of the vector is itself a BrowserItem
          with the usual `.children` API.

        Use this helper anywhere we need to descend; otherwise the walker
        silently drops the entire `user_folders` subtree on the floor.
        """
        children: Any = getattr(node, "children", None)
        if children is not None:
            try:
                return list(children)
            except Exception:
                pass
        try:
            return list(node)
        except Exception:
            return []

    def _diagnose_roots(self, sample_limit: int = 6) -> str:
        """
        Inspect each Browser root and return a compact "root:[child_a,...]"
        string describing the top-level layout. Used as diagnostic detail in
        not_in_browser failures — without this, the client can't tell whether
        `user_library` even exposes children at all on the user's Live build.
        """
        parts: List[str] = []
        for name, root in self._roots():
            try:
                children: List[Any] = self._children_of(root)
                sample: List[str] = []
                for child in children[:sample_limit]:
                    cname: str = (getattr(child, "name", "") or "").strip() or "?"
                    sample.append(cname)
                if len(children) > sample_limit:
                    sample.append("...+%d" % (len(children) - sample_limit))
                parts.append("%s:[%s]" % (name, ",".join(sample)))
            except Exception as e:
                parts.append("%s:<error %s>" % (name, e))
        return " | ".join(parts)

    def _clear_cache(self, params: Tuple[Any, ...] = ()) -> Tuple[str, ...]:
        self._uri_cache.clear()
        return ("ok",)

    def _uri_ends_with_basename(self, uri_lc: str, basename_lc: str) -> bool:
        """
        Check whether `uri_lc` ends with `basename_lc` as a whole path segment.

        A bare `endswith` also matches URIs whose final segment merely ends
        with the target basename (searching for `kick.wav` matches
        `.../sidekick.wav`), which returns the wrong BrowserItem and poisons
        `_uri_cache` for every later load of that path. The character before
        the matched suffix must therefore be a segment separator — `/` or a
        percent-encoded `%2F` (already lowercased to `%2f` here) — or the
        suffix must be the entire URI.
        """
        if not uri_lc.endswith(basename_lc):
            return False
        prefix: str = uri_lc[:-len(basename_lc)]
        return prefix == "" or prefix.endswith("/") or prefix.endswith("%2f")

    def _find_item(self, target_path: str, max_depth: int = 12) -> Optional[Any]:
        """
        Recursively search Browser roots for a BrowserItem matching `target_path`.

        Live's BrowserItem exposes two strings we can match against:
          - `uri`: Live 11+ scheme like `library:/UserLibrary/Samples/Foo.wav`
                  (NOT the on-disk path), often percent-encoded for spaces.
          - `name`: the display name. For audio samples Live typically drops the
                  extension, so a `.wav` file shows as just "Dust On The Desk".

        Match case-insensitively on both `uri` and `name`, with and without
        the extension, so any sample whose basename matches the target wins.
        User Library samples need this: (a) their URIs don't embed the OS
        path, so a substring check against `target_abs` fails; (b) the URI is
        mixed-case, so an `endswith` against a lowercased target never
        matches; and (c) `name` lacks the extension, so a name-equality check
        against the full basename misses.
        """
        target_abs: str = os.path.abspath(target_path)
        target_basename: str = os.path.basename(target_abs)
        target_basename_lc: str = target_basename.lower()
        target_stem_lc: str = os.path.splitext(target_basename)[0].lower()

        if target_abs in self._uri_cache:
            return self._uri_cache[target_abs]

        basename_match: Optional[Any] = None

        def walk(node: Any, depth: int = 0) -> Optional[Any]:
            nonlocal basename_match
            if depth > max_depth:
                return None
            # _children_of handles both BrowserItem (.children) and
            # BrowserItemVector (iterable) shapes. The user_folders subtree
            # root is a vector, not a BrowserItem, so a plain
            # `list(node.children)` would silently drop it — and that subtree
            # is the only place dragged-in custom folders like "Suno Imports"
            # actually live.
            children: List[Any] = self._children_of(node)
            if not children:
                return None
            for child in children:
                try:
                    uri: str = getattr(child, "uri", "") or ""
                    uri_lc: str = uri.lower()
                    name: str = getattr(child, "name", "") or ""
                    name_lc: str = name.lower()
                    is_loadable: bool = bool(getattr(child, "is_loadable", False))

                    # Strongest match: URI contains the absolute OS path. Holds
                    # for `user_folders` roots which Live indexes by path.
                    if target_abs in uri:
                        return child
                    # Case-insensitive segment-boundary suffix match — covers
                    # User Library URIs that encode the filename but in mixed
                    # case, without matching longer basenames that merely end
                    # with the target (e.g. `sidekick.wav` for `kick.wav`).
                    if self._uri_ends_with_basename(uri_lc, target_basename_lc):
                        return child
                    # Last resort: basename (with or without extension) matches
                    # the BrowserItem display name. We only accept loadable
                    # children so folders with the same name don't win.
                    if is_loadable and basename_match is None and (
                        name_lc == target_basename_lc or name_lc == target_stem_lc
                    ):
                        basename_match = child
                except Exception:
                    pass
                # walk() short-circuits on empty children, so descending
                # unconditionally on every non-leaf is fine and lets vectors
                # propagate (a vector child would otherwise be skipped here).
                if getattr(child, "is_folder", False) or not getattr(child, "is_loadable", False):
                    found: Optional[Any] = walk(child, depth + 1)
                    if found is not None:
                        return found
            return None

        for name, root in self._roots():
            self.logger.info("Searching browser root '%s' for %s" % (name, target_basename_lc))
            found: Optional[Any] = walk(root)
            if found is not None:
                self._uri_cache[target_abs] = found
                return found

        if basename_match is not None:
            self.logger.warning("Falling back to basename match for %s" % target_basename_lc)
            self._uri_cache[target_abs] = basename_match
            return basename_match

        return None

    def _highlight_slot(self, track_index: int, clip_index: int) -> Any:
        track: Any = self.song.tracks[track_index]
        slot: Any = track.clip_slots[clip_index]
        self.song.view.selected_track = track
        self.song.view.highlighted_clip_slot = slot
        return slot

    def _focus_session_view(self) -> Optional[str]:
        """
        browser.load_item() drops into the *visible* view's target, not the
        highlighted_clip_slot we just set. If a prior send ended with the UI
        in Arrangement view (e.g. after duplicate_to_arrangement), the next
        load_item silently no-ops — returns cleanly, no engine activity,
        has_clip never flips. Force Session view here so every load lands in
        the slot we highlighted. Returns the previously focused view so the
        caller can restore it once load_item has dispatched.
        """
        try:
            view: Any = Live.Application.get_application().view
            prev_view: Optional[str] = getattr(view, "focused_document_view", None)
            view.focus_view("Session")
            return prev_view
        except Exception as e:
            self.logger.debug("focus_view('Session') failed: %s" % e)
            return None

    def _restore_view(self, view_name: Optional[str]) -> None:
        if not view_name or view_name == "Session":
            return
        try:
            Live.Application.get_application().view.focus_view(view_name)
        except Exception as e:
            self.logger.debug("focus_view('%s') failed: %s" % (view_name, e))

    def _load_file_into_slot(self, params: Tuple[Any, ...]) -> Tuple[Any, ...]:
        if len(params) < 3:
            raise ValueError("/live/clip_slot/load_file expects (track, clip, path)")
        track_index: int = int(params[0])
        clip_index: int = int(params[1])
        file_path: str = str(params[2])

        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            self.logger.error("File not found on disk: %s" % file_path)
            self.osc_server.send("/live/error", ("File not found: %s" % file_path,))
            return (track_index, clip_index, "missing")

        if len(params) > 3 and params[3] is True:
            slot: Any = self.song.tracks[track_index].clip_slots[clip_index]
            if slot.has_clip:
                return (track_index, clip_index, "slot_occupied")
            if not hasattr(slot, "create_audio_clip"):
                return (track_index, clip_index, "not_supported")
            try:
                slot.create_audio_clip(file_path)
            except Exception as error:
                self.logger.error("ClipSlot.create_audio_clip failed: %s", error)
                return (track_index, clip_index, "load_failed")
            return (track_index, clip_index, "ok")

        # Resolve the BrowserItem before touching the slot. not_in_browser is
        # an expected transient (freshly-written files aren't indexed yet and
        # the client retries for ~15 s), so a failed lookup must leave any
        # existing clip in the slot untouched.
        item: Optional[Any] = self._find_item(file_path)
        if item is None:
            # Surface what the walker actually saw — without this, the client
            # has no way to tell whether Live exposes `user_library` at all,
            # whether `Samples` is a top-level child, etc. Format is
            # "root_name:[child_a,child_b,...] | root_name:[...]" so the
            # suno-link terminal can render it verbatim.
            diag: str = self._diagnose_roots()
            msg: str = ("Couldn't locate '%s' in any Live Browser root. "
                   "Roots seen: %s. "
                   "Add its parent folder via /live/browser/add_user_folder, "
                   "or move the file into ~/Music/Ableton/User Library/Samples/"
                   % (file_path, diag))
            self.logger.error(msg)
            self.osc_server.send("/live/error", (msg,))
            # Append the diagnostic as a 4th tuple element. Clients that only
            # inspect the status string (3rd) ignore it; richer clients
            # (suno-link's terminal pane) can render it inline.
            return (track_index, clip_index, "not_in_browser", diag)

        prev_view: Optional[str] = self._focus_session_view()
        slot: Any = self._highlight_slot(track_index, clip_index)
        if slot.has_clip:
            self.logger.info("Slot (%d, %d) already has a clip; deleting before load"
                             % (track_index, clip_index))
            slot.delete_clip()

        try:
            self._browser().load_item(item)
        except Exception as e:
            self.logger.error("browser.load_item failed: %s" % e)
            self.osc_server.send("/live/error", ("load_item failed: %s" % e,))
            self._restore_view(prev_view)
            return (track_index, clip_index, "load_failed")

        # load_item() has dispatched the load against the slot reference;
        # Live's engine processes it asynchronously over the next ~300 ms.
        # Restoring view here is safe — the dispatch decision already used
        # the Session-view target we set above.
        self._restore_view(prev_view)
        return (track_index, clip_index, "ok")

    def _add_user_folder(self, params: Tuple[Any, ...]) -> Tuple[str, ...]:
        """
        Try to register `folder_path` as a Browser User Folder. Live's API doesn't
        formally expose this, so behaviour varies by Live version. As a fallback,
        clear the URI cache so the next search re-walks the (possibly updated)
        Browser tree — the user can also drag the folder into Live's Browser
        manually.
        """
        if len(params) < 1:
            raise ValueError("/live/browser/add_user_folder expects (path,)")
        folder_path: str = str(params[0])
        if not os.path.isdir(folder_path):
            self.osc_server.send("/live/error", ("Folder not found: %s" % folder_path,))
            return ("not_a_folder",)
        b: Any = self._browser()
        added: bool = False
        for attr in ("add_user_folder", "add_to_user_folders"):
            fn: Any = getattr(b, attr, None)
            if callable(fn):
                try:
                    fn(folder_path)
                    added = True
                    break
                except Exception as e:
                    self.logger.info("Browser.%s failed: %s" % (attr, e))
        self._uri_cache.clear()
        return ("ok" if added else "manual_required",)

    def _load_file_into_selected_slot(self, params: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
        if len(params) < 1:
            raise ValueError("/live/browser/load_file expects (path,)")
        slot: Any = self.song.view.highlighted_clip_slot
        if slot is None:
            raise RuntimeError("No clip slot is highlighted")
        track: Any = slot.canonical_parent
        track_index: int = list(self.song.tracks).index(track)
        clip_index: int = list(track.clip_slots).index(slot)
        return self._load_file_into_slot((track_index, clip_index, params[0]))
