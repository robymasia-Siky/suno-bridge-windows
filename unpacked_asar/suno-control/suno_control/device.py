from __future__ import annotations

from typing import Tuple, Any, Callable, List, Optional
from .handler import AbletonOSCHandler

class DeviceHandler(AbletonOSCHandler):
    def __init__(self, manager: Any) -> None:
        super().__init__(manager)
        self.class_identifier: str = "device"

    def init_api(self) -> None:
        def create_device_callback(func: Callable[..., Any], *args: Any, include_ids: bool = False) -> Callable[[Tuple[Any, ...]], Optional[Tuple[Any, ...]]]:
            def device_callback(params: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
                track_index: int = int(params[0])
                device_index: int = int(params[1])
                device: Any = self.song.tracks[track_index].devices[device_index]
                if (include_ids):
                    rv: Any = func(device, *args, params[0:])
                else:
                    rv = func(device, *args, params[2:])

                if rv is not None:
                    return (track_index, device_index, *rv)
                return None

            return device_callback

        methods: List[str] = [
        ]
        properties_r: List[str] = [
            "class_name",
            "name",
            "type"
        ]
        properties_rw: List[str] = [
        ]

        for method in methods:
            self.osc_server.add_handler("/live/device/%s" % method,
                                        create_device_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/device/get/%s" % prop,
                                        create_device_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/device/start_listen/%s" % prop,
                                        create_device_callback(self._start_listen, prop))
            self.osc_server.add_handler("/live/device/stop_listen/%s" % prop,
                                        create_device_callback(self._stop_listen, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/device/set/%s" % prop,
                                        create_device_callback(self._set_property, prop))

        #--------------------------------------------------------------------------------
        # Device: Get/set parameter lists
        #--------------------------------------------------------------------------------
        def device_get_num_parameters(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            return len(device.parameters),

        def device_get_parameters_name(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            return tuple(parameter.name for parameter in device.parameters)

        def device_get_parameters_value(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            return tuple(parameter.value for parameter in device.parameters)

        def device_get_parameters_min(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            return tuple(parameter.min for parameter in device.parameters)

        def device_get_parameters_max(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            return tuple(parameter.max for parameter in device.parameters)

        def device_get_parameters_is_quantized(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            return tuple(parameter.is_quantized for parameter in device.parameters)

        def device_set_parameters_value(device: Any, params: Tuple[Any, ...] = ()) -> None:
            for index, value in enumerate(params):
                device.parameters[index].value = value

        self.osc_server.add_handler("/live/device/get/num_parameters", create_device_callback(device_get_num_parameters))
        self.osc_server.add_handler("/live/device/get/parameters/name", create_device_callback(device_get_parameters_name))
        self.osc_server.add_handler("/live/device/get/parameters/value", create_device_callback(device_get_parameters_value))
        self.osc_server.add_handler("/live/device/get/parameters/min", create_device_callback(device_get_parameters_min))
        self.osc_server.add_handler("/live/device/get/parameters/max", create_device_callback(device_get_parameters_max))
        self.osc_server.add_handler("/live/device/get/parameters/is_quantized", create_device_callback(device_get_parameters_is_quantized))
        self.osc_server.add_handler("/live/device/set/parameters/value", create_device_callback(device_set_parameters_value))

        #--------------------------------------------------------------------------------
        # Device: Get/set individual parameters
        #--------------------------------------------------------------------------------
        def device_get_parameter_value(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            # Cast to ints so that we can tolerate floats from interfaces such as TouchOSC
            # that send floats by default.
            # https://github.com/ideoforms/AbletonOSC/issues/33
            param_index: int = int(params[0])
            return param_index, device.parameters[param_index].value

        # Uses str_for_value method to return the UI-friendly version of a parameter value (ex: "2500 Hz")
        def device_get_parameter_value_string(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            param_index: int = int(params[0])
            return param_index, device.parameters[param_index].str_for_value(device.parameters[param_index].value)

        def device_get_parameter_value_listener(device: Any, params: Tuple[Any, ...] = ()) -> None:

            def property_changed_callback() -> None:
                value: Any = device.parameters[params[2]].value
                self.logger.info("Property %s changed of %s %s: %s" % ('value', 'device parameter', str(params), value))
                self.osc_server.send("/live/device/get/parameter/value", (*params, value,))

                value_string: Any = device.parameters[params[2]].str_for_value(device.parameters[params[2]].value)
                self.logger.info("Property %s changed of %s %s: %s" % ('value_string', 'device parameter', str(params), value_string))
                self.osc_server.send("/live/device/get/parameter/value_string", (*params, value_string,))

            listener_key: Tuple[Any, ...] = ('device_parameter_value', tuple(params))
            if listener_key in self.listener_functions:
               device_get_parameter_remove_value_listener(device, params)

            self.logger.info("Adding listener for %s %s, property: %s" % ('device parameter', str(params), 'value'))
            parameter_object: Any = device.parameters[params[2]]
            parameter_object.add_value_listener(property_changed_callback)
            self.listener_functions[listener_key] = property_changed_callback
            self.listener_objects[listener_key] = parameter_object
            # The listener was attached to a DeviceParameter, not a Device, so
            # the generic `remove_device_parameter_value_listener` lookup in
            # _stop_listen wouldn't resolve. Register the actual remover so
            # _clear_listeners (and explicit stop_listen) clean up correctly.
            self.listener_removers[listener_key] = lambda po=parameter_object, fn=property_changed_callback: po.remove_value_listener(fn)

            property_changed_callback()

        def device_get_parameter_remove_value_listener(device: Any, params: Tuple[Any, ...] = ()) -> None:
            listener_key: Tuple[Any, ...] = ('device_parameter_value', tuple(params))
            if listener_key in self.listener_functions:
                self.logger.info("Removing listener for %s %s, property %s" % (self.class_identifier, str(params), 'value'))
                listener_function: Callable[[], None] = self.listener_functions[listener_key]
                device.parameters[params[2]].remove_value_listener(listener_function)
                self.listener_functions.pop(listener_key, None)
                self.listener_objects.pop(listener_key, None)
                self.listener_removers.pop(listener_key, None)
            else:
                self.logger.warning("No listener function found for property: value (%s)" % (str(params),))

        def device_set_parameter_value(device: Any, params: Tuple[Any, ...] = ()) -> None:
            param_index: int
            param_value: Any
            param_index, param_value = params[:2]
            param_index = int(param_index)
            device.parameters[param_index].value = param_value

        def device_get_parameter_name(device: Any, params: Tuple[Any, ...] = ()) -> Tuple[Any, ...]:
            param_index: int = int(params[0])
            return param_index, device.parameters[param_index].name

        self.osc_server.add_handler("/live/device/get/parameter/value", create_device_callback(device_get_parameter_value))
        self.osc_server.add_handler("/live/device/get/parameter/value_string", create_device_callback(device_get_parameter_value_string))
        self.osc_server.add_handler("/live/device/set/parameter/value", create_device_callback(device_set_parameter_value))
        self.osc_server.add_handler("/live/device/get/parameter/name", create_device_callback(device_get_parameter_name))
        self.osc_server.add_handler("/live/device/start_listen/parameter/value", create_device_callback(device_get_parameter_value_listener, include_ids = True))
        self.osc_server.add_handler("/live/device/stop_listen/parameter/value", create_device_callback(device_get_parameter_remove_value_listener, include_ids = True))
