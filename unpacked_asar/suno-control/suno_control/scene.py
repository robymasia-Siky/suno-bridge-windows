from __future__ import annotations

from .handler import AbletonOSCHandler
from typing import Tuple, Any, Callable, List, Optional

class SceneHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "scene"

    def init_api(self) -> None:
        # TODO: Needs unit tests

        def create_scene_callback(func: Callable[..., Any], *args: Any, include_ids: bool = False) -> Callable[[Tuple[Any, ...]], Optional[Tuple[Any, ...]]]:
            def scene_callback(params: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
                scene_index: int = int(params[0])
                scene: Any = self.song.scenes[scene_index]
                if (include_ids):
                    rv: Any = func(scene, *args, params[0:])
                else:
                    rv = func(scene, *args, params[1:])

                if rv is not None:
                    return (scene_index, *rv)
                return None

            return scene_callback

        methods: List[str] = [
            "fire",
            "fire_as_selected",
        ]
        properties_r: List[str] = [
            "is_empty",
            "is_triggered",
        ]
        properties_rw: List[str] = [
            "color",
            "color_index",
            "name",
            "tempo",
            "tempo_enabled",
            "time_signature_numerator",
            "time_signature_denominator",
            "time_signature_enabled",
        ]

        for method in methods:
            self.osc_server.add_handler("/live/scene/%s" % method, create_scene_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/scene/get/%s" % prop,
                                        create_scene_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/scene/start_listen/%s" % prop,
                                        create_scene_callback(self._start_listen, prop, include_ids=True))
            self.osc_server.add_handler("/live/scene/stop_listen/%s" % prop,
                                        create_scene_callback(self._stop_listen, prop, include_ids=True))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/scene/set/%s" % prop,
                                        create_scene_callback(self._set_property, prop))

        #------------------------------------------------------------------------------------------------
        # The Live API does not have a `fire_selected` Scene method (or class method accessible from Python).
        # This block adds a `fire_selected` method that calls `fire_as_selected` on the selected scene.
        #------------------------------------------------------------------------------------------------
        def scene_fire_selected(params: Tuple[Any, ...] = ()) -> None:
            selected_scene: Any = self.song.view.selected_scene
            if selected_scene:
                selected_scene.fire_as_selected()

        self.osc_server.add_handler("/live/scene/fire_selected", scene_fire_selected)
