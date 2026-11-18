from __future__ import annotations

from typing import Tuple, Any, Callable, Dict, Optional
from ..pythonosc.osc_message import OscMessage, ParseError
from ..pythonosc.osc_bundle import OscBundle, ParseError as BundleParseError
from ..pythonosc.osc_message_builder import OscMessageBuilder, BuildError

import re
import errno
import socket
import logging
import traceback

# Port constants live here (not suno_control/__init__.py) to avoid a circular
# import — __init__.py imports OSCServer from this module. The package
# __init__.py re-exports these as suno_control.OSC_LISTEN_PORT / OSC_RESPONSE_PORT.
OSC_LISTEN_PORT: int = 11000
OSC_RESPONSE_PORT: int = 11001


class OSCServer:
    def __init__(self,
                 local_addr: Tuple[str, int] = ('127.0.0.1', OSC_LISTEN_PORT),
                 remote_addr: Tuple[str, int] = ('127.0.0.1', OSC_RESPONSE_PORT),
                 get_live_set_id: Optional[Callable[[], str]] = None) -> None:
        """
        OSC server with reply-message support.

        Rolls its own UDP socket handling because pythonosc's bundled OSC server
        beachballs Live's main thread when processing incoming messages.

        Args:
            local_addr: Local address and port to listen on. Binds to loopback, so only
                        processes on this machine can reach the interface. The OSC surface is
                        unauthenticated and covers most of the Live Object Model — including
                        track deletion and loading arbitrary on-disk files into clip slots — so
                        binding it to a routable interface would expose that to the network.
            remote_addr: Remote address to send replies to, by default. Can be overridden in send().
        """

        self._local_addr: Tuple[str, int] = local_addr
        self._remote_addr: Tuple[str, int] = remote_addr
        self._response_port: int = remote_addr[1]

        self._socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind(self._local_addr)
        self._callbacks: Dict[str, Callable[..., Any]] = {}
        self._get_live_set_id = get_live_set_id

        self.logger: logging.Logger = logging.getLogger("suno_control")
        self.logger.info("Starting OSC server (local %s, response port %d)",
                         str(self._local_addr), self._response_port)

    def add_handler(self, address: str, handler: Callable[..., Any]) -> None:
        """
        Add an OSC handler.

        Args:
            address: The OSC address string
            handler: A handler function, with signature:
                     params: Tuple[Any, ...]
        """
        self._callbacks[address] = handler

    def clear_handlers(self) -> None:
        """
        Remove all existing OSC handlers.
        """
        self._callbacks = {}

    def send(self,
             address: str,
             params: Tuple[Any, ...] = (),
             remote_addr: Optional[Tuple[str, int]] = None) -> None:
        """
        Send an OSC message.

        Args:
            address: The OSC address (e.g. /frequency)
            params: A tuple of zero or more OSC params
            remote_addr: The remote address to send to, as a 2-tuple (hostname, port).
                         If None, uses the default remote address.
        """
        msg_builder: OscMessageBuilder = OscMessageBuilder(address)
        for param in params:
            msg_builder.add_arg(param)

        try:
            msg = msg_builder.build()
            if remote_addr is None:
                remote_addr = self._remote_addr
            self._socket.sendto(msg.dgram, remote_addr)
        except BuildError:
            self.logger.error("Suno Bridge: OSC build error: %s" % (traceback.format_exc()))
        except OSError as exc:
            #--------------------------------------------------------------------------------
            # sendto can fail at the socket layer — e.g. EMSGSIZE when a reply
            # (such as the notes of a very large clip) exceeds the UDP datagram
            # limit. The reply is lost either way; propagating would also abort
            # the caller's datagram drain loop, so log and swallow.
            #--------------------------------------------------------------------------------
            self.logger.error("Suno Bridge: OSC send to %s failed (%d-byte datagram): %s"
                              % (address, len(msg.dgram), exc))

    def _send_handler_error(self, original_address: str, exc: Exception, remote_addr: Tuple[str, int]) -> None:
        """
        Notify the caller that a handler raised. Sent on `/live/handler/error`
        with (original_address, error_class_name, message). The exact-match
        case calls this from process_message; without it, an exception in a
        handler returns no reply and the client times out blind.
        """
        self.logger.error("Suno Bridge: Handler %s raised %s: %s\n%s",
                          original_address, type(exc).__name__, exc, traceback.format_exc())
        try:
            remote_hostname, _ = remote_addr
            response_addr: Tuple[str, int] = (remote_hostname, self._response_port)
            self.send(address="/live/handler/error",
                      params=(original_address, type(exc).__name__, str(exc)),
                      remote_addr=response_addr)
        except Exception:
            self.logger.warning("Suno Bridge: failed to send /live/handler/error: %s"
                                % traceback.format_exc())

    def process_message(self, message: Any, remote_addr: Tuple[str, int]) -> None:
        callback_address = message.address
        if message.address.startswith("/live/guard/"):
            try:
                guard = re.fullmatch(r"/live/guard/([A-Za-z0-9_-]+)(/[^*]+)", message.address)
                if guard is None:
                    raise ValueError("Malformed guarded OSC address")
                callback_address = "/live" + guard.group(2)
                if callback_address not in self._callbacks:
                    raise ValueError("Unknown guarded OSC target")
                if self._get_live_set_id is None:
                    raise RuntimeError("Native Live Set identity is unavailable; update Suno Bridge")
                if self._get_live_set_id() != guard.group(1):
                    raise RuntimeError("The target Live Set changed")
            except Exception as exc:
                self._send_handler_error(message.address, exc, remote_addr)
                return
        if callback_address in self._callbacks:
            callback: Callable[..., Any] = self._callbacks[callback_address]
            try:
                rv: Any = callback(message.params)
            except Exception as exc:
                self._send_handler_error(message.address, exc, remote_addr)
                return

            if rv is not None:
                assert isinstance(rv, tuple)
                remote_hostname, _ = remote_addr
                response_addr: Tuple[str, int] = (remote_hostname, self._response_port)
                self.send(address=message.address,
                          params=rv,
                          remote_addr=response_addr)
        elif "*" in message.address:
            #--------------------------------------------------------------------------------
            # A wildcard stands in for exactly one address part, so the pattern has to
            # match the whole handler address. Matching a prefix instead would make
            # /live/song/* fan out across every handler under it, firing side effects
            # (undo, capture_midi, trigger_session_record) that the sender never named.
            #--------------------------------------------------------------------------------
            regex: str = message.address.replace("*", "[^/]+")
            for callback_address, callback in self._callbacks.items():
                if re.fullmatch(regex, callback_address):
                    try:
                        rv = callback(message.params)
                    except ValueError:
                        #--------------------------------------------------------------------------------
                        # Don't throw errors for queries that require more arguments
                        # (e.g. /live/track/get/send with no args)
                        #--------------------------------------------------------------------------------
                        continue
                    except AttributeError:
                        #--------------------------------------------------------------------------------
                        # Don't throw errors when trying to create listeners for properties that can't
                        # be listened for (e.g. can_be_armed, is_foldable)
                        #--------------------------------------------------------------------------------
                        continue
                    except Exception as exc:
                        #--------------------------------------------------------------------------------
                        # Route any other handler exception to /live/handler/error, matching the
                        # exact-match dispatch above, and keep dispatching to the remaining matched
                        # callbacks. An escaping exception is swallowed by process()'s generic
                        # handler with no structured reply, and aborts the datagram drain loop
                        # mid-tick — delaying every queued datagram behind it.
                        #--------------------------------------------------------------------------------
                        self._send_handler_error(callback_address, exc, remote_addr)
                        continue
                    if rv is not None:
                        assert isinstance(rv, tuple)
                        remote_hostname, _ = remote_addr
                        response_addr = (remote_hostname, self._response_port)
                        self.send(address=callback_address,
                                  params=rv,
                                  remote_addr=response_addr)
        else:
            self.logger.error("Suno Bridge: Unknown OSC address: %s" % message.address)

    def process_bundle(self, bundle: Any, remote_addr: Tuple[str, int]) -> None:
        for i in bundle:
            if OscBundle.dgram_is_bundle(i.dgram):
                self.process_bundle(i, remote_addr)
            else:
                self.process_message(i, remote_addr)

    def parse_bundle(self, data: bytes, remote_addr: Tuple[str, int]) -> None:
        if OscBundle.dgram_is_bundle(data):
            try:
                bundle: OscBundle = OscBundle(data)
                self.process_bundle(bundle, remote_addr)
            except (BundleParseError, ParseError, RecursionError):
                self.logger.error("Suno Bridge: Error parsing OSC bundle: %s" % (traceback.format_exc()))
        else:
            try:
                message: OscMessage = OscMessage(data)
                self.process_message(message, remote_addr)
            except ParseError:
                self.logger.error("Suno Bridge: Error parsing OSC message: %s" % (traceback.format_exc()))

    def process(self) -> None:
        """
        Synchronously process all data queued on the OSC socket.
        """
        try:
            while True:
                #--------------------------------------------------------------------------------
                # Loop until no more data is available.
                #--------------------------------------------------------------------------------
                data: bytes
                remote_addr_recv: Tuple[str, int]
                data, remote_addr_recv = self._socket.recvfrom(65536)
                #--------------------------------------------------------------------------------
                # Update the default reply address to the most recent client. Used when
                # sending (e.g) /live/song/beat messages and listen updates.
                #
                # This is slightly ugly and prevents registering listeners from different IPs.
                #--------------------------------------------------------------------------------
                self._remote_addr = (remote_addr_recv[0], OSC_RESPONSE_PORT)
                self.parse_bundle(data, remote_addr_recv)

        except socket.error as e:
            if e.errno == errno.ECONNRESET:
                #--------------------------------------------------------------------------------
                # This benign error seems to occur on startup on Windows
                #--------------------------------------------------------------------------------
                self.logger.warning("Suno Bridge: Non-fatal socket error: %s" % (traceback.format_exc()))
            elif e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                #--------------------------------------------------------------------------------
                # Another benign networking error, throw when no data is received
                # on a call to recvfrom() on a non-blocking socket
                #--------------------------------------------------------------------------------
                pass
            else:
                #--------------------------------------------------------------------------------
                # Something more serious has happened
                #--------------------------------------------------------------------------------
                self.logger.error("Suno Bridge: Socket error: %s" % (traceback.format_exc()))

        except Exception as e:
            self.logger.error("Suno Bridge: Error handling OSC message: %s" % e)
            self.logger.warning("Suno Bridge: %s" % traceback.format_exc())

    def shutdown(self) -> None:
        """
        Shutdown the server network sockets.
        """
        self._socket.close()
