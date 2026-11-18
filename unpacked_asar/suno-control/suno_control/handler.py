from __future__ import annotations

from ableton.v2.control_surface.component import Component
from typing import Optional, Tuple, Any, Dict, Callable
import logging
from .osc_server import OSCServer

class AbletonOSCHandler(Component):
    def __init__(self, manager: Any) -> None:
        super().__init__()

        self.logger: logging.Logger = logging.getLogger("suno_control")
        self.manager: Any = manager
        self.osc_server: OSCServer = self.manager.osc_server
        self.listener_functions: Dict[Tuple[Any, ...], Callable[[], None]] = {}
        self.listener_objects: Dict[Tuple[Any, ...], Any] = {}
        # Optional override-removers for listeners that don't fit the generic
        # `target.remove_<prop>_listener(fn)` shape — e.g. mixer listeners
        # (which live on `track.mixer_device.<prop>`, not on the Track) and
        # device parameter listeners (which live on a DeviceParameter object).
        # _clear_listeners and _stop_listen prefer the registered closure
        # over the generic getattr path when present.
        self.listener_removers: Dict[Tuple[Any, ...], Callable[[], None]] = {}
        self.class_identifier: Optional[str] = None
        # init_api runs last so subclasses overriding it can rely on the
        # listener registries existing — registers OSC handlers that may
        # capture `self` and reference these dicts when invoked later.
        self.init_api()

    def init_api(self) -> None:
        pass

    def clear_api(self) -> None:
        self._clear_listeners()

    #--------------------------------------------------------------------------------
    # Generic callbacks
    #--------------------------------------------------------------------------------
    def _call_method(self, target: Any, method: str, params: Optional[Tuple[Any, ...]] = ()) -> None:
        self.logger.info("Calling method for %s: %s (params %s)" % (self.class_identifier, method, str(params)))
        getattr(target, method)(*params)

    def _set_property(self, target: Any, prop: str, params: Tuple[Any, ...]) -> None:
        self.logger.info("Setting property for %s: %s (new value %s)" % (self.class_identifier, prop, params[0]))
        setattr(target, prop, params[0])

    def _get_property(self, target: Any, prop: str, params: Optional[Tuple[Any, ...]] = ()) -> Tuple[Any, ...]:
        try:
            value: Any = getattr(target, prop)
        except RuntimeError:
            #--------------------------------------------------------------------------------
            # Gracefully handle errors, which may occur when querying parameters that don't apply
            # to a particular object (e.g. track.fold_state for a non-group track)
            #--------------------------------------------------------------------------------
            value = None
        self.logger.info("Getting property for %s: %s = %s" % (self.class_identifier, prop, value))
        return (value, *params)

    def _start_listen(self, target: Any, prop: str, params: Optional[Tuple[Any, ...]] = (), getter: Optional[Callable[..., Any]] = None) -> None:
        """
        Start listening for the property named `prop` on the Live object `target`.
        `params` is typically a tuple containing the track/clip index.

        getter can be used for a customer getter when we're accessing native objects
        e.g. in view.py we don't return the selected_scene, but the selected_scene index.

        Args:
            target:
            prop:
            params:
            getter:
        """
        def property_changed_callback() -> None:
            if getter is None:
                value: Any = getattr(target, prop)
            else:
                value = getter(params)
            if type(value) is not tuple:
                value = (value,)
            self.logger.info("Property %s changed of %s %s: %s" % (prop, self.class_identifier, str(params), value))
            osc_address: str = "/live/%s/get/%s" % (self.class_identifier, prop)
            self.osc_server.send(osc_address, (*params, *value,))

        listener_key: Tuple[Any, ...] = (prop, tuple(params))
        if listener_key in self.listener_functions:
            self._stop_listen(target, prop, params)

        self.logger.info("Adding listener for %s %s, property: %s" % (self.class_identifier, str(params), prop))
        add_listener_function_name: str = "add_%s_listener" % prop
        add_listener_function: Callable[..., None] = getattr(target, add_listener_function_name)
        add_listener_function(property_changed_callback)
        self.listener_functions[listener_key] = property_changed_callback
        self.listener_objects[listener_key] = target
        #--------------------------------------------------------------------------------
        # Immediately send the current value
        #--------------------------------------------------------------------------------
        property_changed_callback()

    def _stop_listen(self, target: Any, prop: str, params: Optional[Tuple[Any, ...]] = ()) -> None:
        listener_key: Tuple[Any, ...] = (prop, tuple(params))
        if listener_key in self.listener_functions:
            self.logger.info("Removing listener for %s %s, property %s" % (self.class_identifier, str(params), prop))
            listener_function: Callable[[], None] = self.listener_functions[listener_key]
            remover: Optional[Callable[[], None]] = self.listener_removers.get(listener_key)
            try:
                if remover is not None:
                    remover()
                else:
                    remove_listener_function: Callable[..., None] = getattr(target, "remove_%s_listener" % prop)
                    remove_listener_function(listener_function)
            except Exception as e:
                #--------------------------------------------------------------------------------
                # Benign when an observer is no longer connected (deleted clip,
                # detached parameter), or when a non-generic listener was
                # misrouted here. Either way, fall through and drop registry
                # state so cleanup continues for the remaining listeners.
                #--------------------------------------------------------------------------------
                self.logger.info("Exception whilst removing listener (likely benign): %s" % e)

            self.listener_functions.pop(listener_key, None)
            self.listener_objects.pop(listener_key, None)
            self.listener_removers.pop(listener_key, None)
        else:
            self.logger.warning("No listener function found for property: %s (%s)" % (prop, str(params)))

    def _clear_listeners(self) -> None:
        """
        Clears all listener functions, to prevent listeners continuing to report after a reload.
        """
        for listener_key in list(self.listener_functions.keys()):
            try:
                prop: str
                params_raw: Any
                prop, params_raw = listener_key
                # listener_objects may legitimately be missing an entry for
                # listeners registered via a custom remover (which doesn't
                # need a target). Fall back to None — _stop_listen will use
                # the remover path when present.
                target: Any = self.listener_objects.get(listener_key)
                self._stop_listen(target, prop, params_raw)
            except Exception as e:
                self.logger.warning("Failed to clear listener %s: %s" % (listener_key, e))
                self.listener_functions.pop(listener_key, None)
                self.listener_objects.pop(listener_key, None)
                self.listener_removers.pop(listener_key, None)
