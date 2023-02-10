#!/usr/bin/env python
# License: GPLv3 Copyright: 2021, Kovid Goyal <kovid at kovidgoyal.net>

import sys
from typing import List, Optional

from kitty.cli import parse_args
from kitty.cli_stub import RCOptions, ResizeCLIOptions
from kitty.constants import version

from kitty.rc.base import command_for_name, parse_subcommand_cli
from kitty.remote_control import encode_send, parse_rc_args

from ..show_key.kitty_mode import format_mods
from ..tui.handler import Handler
from ..tui.loop import Loop, MouseEvent, EventType, MouseButton
from ..tui.operations import MouseTracking

global_opts = RCOptions()

class Mouse(Handler):
    mouse_tracking = MouseTracking.full

    def __init__(self, opts: ResizeCLIOptions):
        self.current_mouse_event: Optional[MouseEvent] = None
        self.opts = opts
        self.previous_cell = None
        self.current_cell = None

    def initialize(self) -> None:
        global global_opts
        global_opts = parse_rc_args(['kitty', '@resize-window'])[0]
        self.original_size = self.screen_size
        self.cmd.set_cursor_visible(False)
        self.draw_screen()

    def finalize(self) -> None:
        self.cmd.set_cursor_visible(True)

    def on_mouse_event(self, ev: MouseEvent) -> None:
        # TODO: Can we remove this?
        self.current_mouse_event = ev

        # Ignore mouse button press events
        if ev.type == EventType.PRESS:
            return

        # Ignore mouse button release events unless it's right click, in which
        # case we are done
        if ev.type == EventType.RELEASE:
            if MouseButton.RIGHT in ev.buttons:
                self.quit_loop(0)
            return

        self.on_mouse_move(ev)

    def on_mouse_move(self, ev: MouseEvent) -> None:
        self.current_cell = (int(ev.cell_x), int(ev.cell_y))

        if self.previous_cell == None:
            self.previous_cell = self.current_cell
            return

        redraw_pending = False

        horizontal_multiplier = self.current_cell[0] - self.previous_cell[0]
        if not horizontal_multiplier == 0:
            is_decrease = horizontal_multiplier < 0
            self.do_window_resize(is_decrease=is_decrease, multiplier=abs(horizontal_multiplier))
            redraw_pending = True

        vertical_multiplier = self.current_cell[1] - self.previous_cell[1]
        if not vertical_multiplier == 0:
            is_decrease = vertical_multiplier < 0
            self.do_window_resize(is_horizontal=False, is_decrease=is_decrease, multiplier=abs(vertical_multiplier))
            redraw_pending = True

        if redraw_pending:
            self.draw_screen()

        self.previous_cell = (self.current_cell[0], self.current_cell[1])

    def do_window_resize(self, is_decrease: bool = False, is_horizontal: bool = True, reset: bool = False, multiplier: int = 1) -> None:
        resize_window = command_for_name('resize_window')
        increment = self.opts.horizontal_increment if is_horizontal else self.opts.vertical_increment
        increment *= multiplier
        if is_decrease:
            increment *= -1
        axis = 'reset' if reset else ('horizontal' if is_horizontal else 'vertical')
        cmdline = [resize_window.name, '--self', f'--increment={increment}', '--axis=' + axis]
        opts, items = parse_subcommand_cli(resize_window, cmdline)
        payload = resize_window.message_to_kitty(global_opts, opts, items)
        send = {'cmd': resize_window.name, 'version': version, 'payload': payload, 'no_response': False}
        self.write(encode_send(send))


    @Handler.atomic_update
    def draw_screen(self) -> None:
        self.cmd.clear_screen()
        ev = self.current_mouse_event

        self.print('Resizing window')
        self.print('Move the mouse to resize the window')
        self.print('Release the right mouse button to stop resizing')

        if ev is not None:
            self.print('Debug info:')
            self.print(f'Position: {ev.pixel_x}, {ev.pixel_y}')
            self.print(f'Previous Cell: {ev.cell_x}, {ev.cell_y}')
            self.print(f'Current Cell:  {ev.cell_x}, {ev.cell_y}')

    def on_interrupt(self) -> None:
        self.quit_loop(0)
    on_eot = on_interrupt

OPTIONS = r'''
--horizontal-increment
default=2
type=int
The base horizontal increment.


--vertical-increment
default=2
type=int
The base vertical increment.
'''.format

def main(args: List[str]) -> None:
    msg = 'Resize the current window'
    try:
        cli_opts, items = parse_args(args[1:], OPTIONS, '', msg, 'mouse_resize', result_class=ResizeCLIOptions)
    except SystemExit as e:
        if e.code != 0:
            print(e.args[0], file=sys.stderr)
            input('Press Enter to quit')
        return

    loop = Loop()
    handler = Mouse(cli_opts)
    loop.loop(handler)


if __name__ == '__main__':
    main(sys.argv)
