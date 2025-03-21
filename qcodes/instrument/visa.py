"""Visa instrument driver based on pyvisa."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pyvisa
import pyvisa.constants as vi_const
import pyvisa.resources

from .base import Instrument
from .base import InstrumentBase
import qcodes.utils.validators as vals

#from qcodes.logger import get_instrument_logger
from qcodes.utils.delaykeyboardinterrupt import DelayedKeyboardInterrupt


VISA_LOGGER = '.'.join((InstrumentBase.__module__, 'com', 'visa'))

log = logging.getLogger(__name__)

def listVISAinstruments(baudrates='qdac'):
    """
    List the VISA instruments connected to the computer.
    If you are expecting instrument(s), e.g. QDAC, to communicate with a baudrate other than 9600,
    you can include the possible baudrates when calling the function. By default it also checks for the
    baudrate used by the qdac. If you want to check other baudrates, include them explicitly as a list,
    or use predefined lists 'standard' or 'all'
    """
    baudrate_library={'qdac':[921600],
                'standard':[460800,230400,115200,57600,38400,19200,14400,4800,2400,1200,600,300],
                'all':[921600,256000,153600,128000,56000,28800,110,460800,230400,115200,57600,38400,19200,14400,4800,2400,1200,600,300]}

    if type(baudrates) is int:
        if baudrates not in baudrate_library['all']:
            print(f'{baudrates} is not usually a supported baudrate: Check for typo')
        baudrates=[baudrates]
    elif type(baudrates) is str:
        if baudrates in ['qdac','standard','all']:
            baudrates=baudrate_library[baudrates]
        else:
            raise ValueError('baudrates must be one of \'qdac\', \'standard\' or \'all\' if providing string')
    elif type(baudrates) is list:
        for baudrate in baudrates:
            if baudrate not in baudrate_library['all']:
                print(f'{baudrate} is not usually a supported baudrate: Check for typo')
    else:
        raise TypeError('baudrates must be either an integer, list of integers, or one of \'qdac\', \'standard\' or \'all\'')

    resman=pyvisa.ResourceManager()
    for resource in resman.list_resources():
        try:
            res=resman.open_resource(resource)
            print(resource,'\n',res.query('*IDN?'))
        except:
            for baudrate in baudrates:
                connected=False
                try:
                    res=resman.open_resource(resource)
                    res.baud_rate=baudrate
                    print(resource,'\n',res.query('*IDN?'))
                    connected=True
                    break
                except Exception as e:
                    pass
                finally:
                    res.baud_rate=9600
            if connected==False:
                print(f'Cannot access {resource}. Likely the instrument is already connected.')

class VisaInstrument(Instrument):

    """
    Base class for all instruments using visa connections.

    Args:
        name: What this instrument is called locally.
        address: The visa resource name to use to connect.
        timeout: seconds to allow for responses. Default 5.
        terminator: Read and write termination character(s).
            If None the terminator will not be set and we
            rely on the defaults from PyVisa. Default None.
        device_clear: Perform a device clear. Default True.
        visalib: Visa backend to use when connecting to this instrument.
            This should be in the form of a string '<pathtofile>@<backend>'.
            Both parts can be omitted and pyvisa will try to infer the
            path to the visa backend file.
            By default the IVI backend is used if found, but '@py' will use the
            ``pyvisa-py`` backend. Note that QCoDeS does not install (or even require)
            ANY backends, it is up to the user to do that. see eg:
            http://pyvisa.readthedocs.org/en/stable/names.html
        metadata: additional static metadata to add to this
            instrument's JSON snapshot.

    See help for :class:`.Instrument` for additional information on writing
    instrument subclasses.

    """

    def __init__(
        self,
        name: str,
        address: str,
        timeout: float = 5,
        terminator: str | None = None,
        device_clear: bool = True,
        visalib: str | None = None,
        **kwargs: Any,
    ):

        super().__init__(name, **kwargs)
        #self.visa_log = get_instrument_logger(self, VISA_LOGGER)

        self.add_parameter('timeout',
                           get_cmd=self._get_visa_timeout,
                           set_cmd=self._set_visa_timeout,
                           unit='s',
                           vals=vals.MultiType(vals.Numbers(min_value=0),
                                               vals.Enum(None)))

        try:
            visa_handle, visabackend = self._open_resource(address, visalib)
        except Exception as e:
            log.exception(f"Could not connect at {address}")
            self.close()
            raise e

        self.visabackend: str = visabackend
        self.visa_handle: pyvisa.resources.MessageBasedResource = visa_handle
        """
        The VISA resource used by this instrument.
        """
        self.visalib: str | None = visalib
        self._address = address

        if device_clear:
            self.device_clear()

        self.set_terminator(terminator)
        self.timeout.set(timeout)

    def _open_resource(
        self, address: str, visalib: str | None
    ) -> tuple[pyvisa.resources.MessageBasedResource, str]:

        # in case we're changing the address - close the old handle first
        if getattr(self, "visa_handle", None):
            self.visa_handle.close()

        if visalib is not None:
            log.info(
                f"Opening PyVISA Resource Manager with visalib: {visalib}"
            )
            resource_manager = pyvisa.ResourceManager(visalib)
            visabackend = visalib.split("@")[1]
        else:
            log.info("Opening PyVISA Resource Manager with default backend.")
            resource_manager = pyvisa.ResourceManager()
            visabackend = "ivi"

        log.info(f"Opening PyVISA resource at address: {address}")
        resource = resource_manager.open_resource(address)
        if not isinstance(resource, pyvisa.resources.MessageBasedResource):
            resource.close()
            raise TypeError("QCoDeS only support MessageBasedResource Visa resources")

        return resource, visabackend

    def set_address(self, address: str) -> None:
        """
        Set the address for this instrument.

        Args:
            address: The visa resource name to use to connect. The address
                should be the actual address and just that. If you wish to
                change the backend for VISA, use the self.visalib attribute
                (and then call this function).
        """
        resource, visabackend = self._open_resource(address, self.visalib)
        self.visa_handle = resource
        self._address = address
        self.visabackend = visabackend

    def device_clear(self) -> None:
        """Clear the buffers of the device"""

        # Serial instruments have a separate flush method to clear
        # their buffers which behaves differently to clear. This is
        # particularly important for instruments which do not support
        # SCPI commands.

        # Simulated instruments do not support a handle clear
        if self.visabackend == 'sim':
            return

        flush_operation = (
                vi_const.BufferOperation.discard_read_buffer_no_io |
                vi_const.BufferOperation.discard_write_buffer
        )

        if isinstance(self.visa_handle, pyvisa.resources.SerialInstrument):
            self.visa_handle.flush(flush_operation)
        else:
            self.visa_handle.clear()

    def set_terminator(self, terminator: str | None) -> None:
        r"""
        Change the read terminator to use.

        Args:
            terminator: Character(s) to look for at the end of a read and
                to end each write command with.
                eg. ``\r\n``. If None the terminator will not be set.
        """
        if terminator is not None:
            self.visa_handle.write_termination = terminator
            self.visa_handle.read_termination = terminator

    def _set_visa_timeout(self, timeout: float | None) -> None:
        # according to https://pyvisa.readthedocs.io/en/latest/introduction/resources.html#timeout
        # both float('+inf') and None are accepted as meaning infinite timeout
        # however None does not pass the typechecking in 1.11.1
        if timeout is None:
            self.visa_handle.timeout = float('+inf')
        else:
            # pyvisa uses milliseconds but we use seconds
            self.visa_handle.timeout = timeout * 1000.0

    def _get_visa_timeout(self) -> float | None:

        timeout_ms = self.visa_handle.timeout
        if timeout_ms is None:
            return None
        else:
            # pyvisa uses milliseconds but we use seconds
            return timeout_ms / 1000

    def close(self) -> None:
        """Disconnect and irreversibly tear down the instrument."""
        if getattr(self, 'visa_handle', None):
            self.visa_handle.close()
        super().close()

    def write_raw(self, cmd: str) -> None:
        """
        Low-level interface to ``visa_handle.write``.

        Args:
            cmd: The command to send to the instrument.
        """
        with DelayedKeyboardInterrupt():
            log.debug(f"Writing: {cmd}")
            self.visa_handle.write(cmd)

    def ask_raw(self, cmd: str) -> str:
        """
        Low-level interface to ``visa_handle.ask``.

        Args:
            cmd: The command to send to the instrument.

        Returns:
            str: The instrument's response.
        """
        with DelayedKeyboardInterrupt():
            log.debug(f"Querying: {cmd}")
            response = self.visa_handle.query(cmd)
            log.debug(f"Response: {response}")
        return response

    def snapshot_base(
        self,
        update: bool | None = True,
        params_to_skip_update: Sequence[str] | None = None,
    ) -> dict[Any, Any]:
        """
        State of the instrument as a JSON-compatible dict (everything that
        the custom JSON encoder class :class:`.NumpyJSONEncoder`
        supports).

        Args:
            update: If True, update the state by querying the
                instrument. If None only update if the state is known to be
                invalid. If False, just use the latest values in memory and
                never update.
            params_to_skip_update: List of parameter names that will be skipped
                in update even if update is True. This is useful if you have
                parameters that are slow to update but can be updated in a
                different way (as in the qdac). If you want to skip the
                update of certain parameters in all snapshots, use the
                ``snapshot_get``  attribute of those parameters instead.
        Returns:
            dict: base snapshot
        """
        snap = super().snapshot_base(update=update,
                                     params_to_skip_update=params_to_skip_update)

        snap["address"] = self._address
        snap["terminator"] = self.visa_handle.read_termination
        snap["read_terminator"] = self.visa_handle.read_termination
        snap["write_terminator"] = self.visa_handle.write_termination
        snap["timeout"] = self.timeout.get()

        return snap
