from QSwitch_elab import QSwitch
import numpy as np
from typing import (
    Tuple, Sequence, Dict, Union, Optional, ArrayLike)
import os
import json

relays_per_line = 9
relay_lines = 24

State = Sequence[Tuple[int, int]]

OneOrMore = Union[str, Sequence[str]]

class QSwitches():
    def __init__(self, qswitch: list[QSwitch], default_names: Optional[ArrayLike]=None):
        self.qswitches = qswitch
        # self.num_of_qswitches = len(qswitch)
        self._set_default_names(default_names)



    def reset(self) -> None:
        for qswitch in self.qswitches:
            qswitch.reset()


    # -----------------------------------------------------------------------
    # Direct manipulation of the relays
    # -----------------------------------------------------------------------

    def open_relay(self, line: int, tap: int) -> None:
        lin = self._line_names.index(line)
        qswitch = self.qswitches[lin//relay_lines]
        switch_line = lin%relay_lines + 1

        qswitch.open_relay(switch_line, tap)
  
    
    def close_relay(self, line: int, tap: int) -> None:
        lin = self._line_names.index(line)
        qswitch = self.qswitches[lin//relay_lines]
        switch_line = lin%relay_lines + 1

        qswitch.close_relay(switch_line, tap)


    # def close_relays(self, relays: State) -> None:
    #     for line, tap in relays:
    #         if line <=24:
    #             self.qswitches[0].close_relay(line, tap)
    #         else:
    #             self.qswitches[1].close_relay(line-26, tap)

    # def open_relays(self, relays: State) -> None:
    #     for line, tap in relays:
    #         if line <=24:
    #             self.qswitches[0].open_relay(line, tap)
    #         else:
    #             self.qswitches[1].open_relay(line-26, tap)



    def save_state(self, name: str) -> None:
        """Save the current state of the relays

        Args:
            name (str): Name of the saved state
        """
        try:
            # Determine the directory of the Jupyter Notebook
            notebook_dir = os.getcwd()
            savedstates_path = os.path.join(notebook_dir, 'multisavedstates.json')

            # Load existing states if the file exists
            try:
                with open(savedstates_path, 'r') as f:
                    savedstates = json.load(f)
            except FileNotFoundError:
                savedstates = {}

            # Add the current state to the saved states
            savedstates[name] = {}
            for qswitch in self.qswitches:
                state = qswitch.get_state()
                serial = qswitch.IDN()['serial']

                savedstates[name][serial] = state

            # Write the updated states back to the file
            with open(savedstates_path, 'w') as f:
                json.dump(savedstates, f, indent=4)

        except Exception as e:
            raise ValueError(f"Failed to save state: {e}")
        

    def load_state(self, name: str) -> None:
        """Load a saved state of the relays

        Args:
            name (str): Name of the saved state
            
        """
        try:
            notebook_dir = os.getcwd()
            savedstates_path = os.path.join(notebook_dir, 'multisavedstates.json')


            with open(savedstates_path, 'r') as f:
                savedstates = json.load(f)

            if name in savedstates:
                for qswitch in self.qswitches:
                    serial = qswitch.IDN()['serial']
                    if serial in savedstates[name]:
                        state = savedstates[name][serial]
                        qswitch.set_state(state)
                    else:
                        raise ValueError(f"State for QSwitch with serial {serial} not found.")
                self._set_state(savedstates[name])
            else:
                raise ValueError(f"State '{name}' not found.")

        except FileNotFoundError:
            raise ValueError("No saved states found.")
        except Exception as e:
            raise ValueError(f"Failed to load state: {e}")
        

    def saved_states(self) -> Dict[str, Dict[str, State]]:
        """Get the saved states of the relays

        Returns:
            Dict[str, Dict[str, State]]: Dictionary of saved states
        """
        try:
            notebook_dir = os.getcwd()
            savedstates_path = os.path.join(notebook_dir, 'multisavedstates.json')

            with open(savedstates_path, 'r') as f:
                savedstates = json.load(f)

            return savedstates

        except FileNotFoundError:
            raise ValueError("No saved states found.")
        except Exception as e:
            raise ValueError(f"Failed to load saved states: {e}")
    
    # -----------------------------------------------------------------------
    # Manipulation by name
    # -----------------------------------------------------------------------

    def arrange(self, breakouts: Optional[Dict[str, int]] = None,
                lines: Optional[Dict[str, int]] = None) -> None:
 
        if breakouts:
            for name, tap in breakouts.items():
                for qswitch in self.qswitches:
                    qswitch._tap_names[name] = tap

        if lines:
            for name, line in lines.items():
                self.qswitches[line-1//relay_lines]._line_names[name] = line
          


    def breakout(self, line : str, tap: str) -> None:
        self.qswitches[(self._to_line(line)-1)//relay_lines].breakout(self._to_line(line), self._to_tap(tap))

    
    def ground(self, lines: OneOrMore) -> None:
        lines = self._to_line(lines)
        for line in lines:
            self.qswitches[(self._to_line(line)-1)//relay_lines].ground(line)


    def connect(self, lines: OneOrMore) -> None:
        lines = self._to_line(lines)
        for line in lines:
            self.qswitches[(self._to_line(line)-1)//relay_lines].connect(line)


    def lineFloat(self, lines: OneOrMore) -> None:
        lines = self._to_line(lines)
        for line in lines:
            self.qswitches[(self._to_line(line)-1)//relay_lines].lineFloat(line)



    # -----------------------------------------------------------------------
    # Internal methods
    # -----------------------------------------------------------------------


    def _set_default_names(self, default_names: Optional[ArrayLike] = None) -> None:
        if default_names:
            lines = default_names
        else:
            lines = np.concatenate((np.arange(1, relay_lines*len(self.qswitches))))
        taps = range(1, relays_per_line)
        self._line_names = dict(zip(map(str, lines), lines))
        self._tap_names = dict(zip(map(str, taps), taps))


    def _to_line(self, name: str) -> int:
        try:
            return self._line_names[name]
        except KeyError:
            raise ValueError(f'Unknown line "{name}"')

    def _to_tap(self, name: str) -> int:
        try:
            return self._tap_names[name]
        except KeyError:
            raise ValueError(f'Unknown tap "{name}"')