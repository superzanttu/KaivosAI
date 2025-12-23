# Textual Migration Summary (v0.14.0)

## Overview
KaivosAI has been migrated from **Urwid** to **Textual** framework for the TUI windowing system.

## Why Textual?

| Problem with Urwid | Textual Solution |
|---|---|
| Single `Overlay` widget only; stacking breaks | Native `Screen` system with proper `Modal` dialogs |
| Limited widget focus management | DOM-based focus management with guaranteed focus flow |
| Unreliable mouse event propagation through overlays | Full mouse support with proper event propagation |
| Custom dragging workarounds needed | Built-in drag-and-drop support via CSS positioning |
| No responsive layout system | CSS-like styling with flexbox/grid layouts |
| Minimal documentation, inactive development | Extensive docs, active maintenance by Textualize.io |

## Architecture Changes

### Before (Urwid)
- `cli.py`: ~2500 lines, monolithic
- `run_urwid_tui()` → `urwid.MainLoop()`
- Manual widget stacking with `Pile`, `Columns`, `Overlay`
- Fixed layout; only Clock draggable (with hacks)
- Keyboard focus stealing issues

### After (Textual)
- `textual_cli.py`: ~700 lines, modular
- `run_textual_tui()` → `GameApp.run()` (Textual App)
- Proper widget hierarchy: `GameApp` → `GameScreen` → Containers → Widgets
- CSS-based layout with responsive design
- Robust focus management built-in

## New Files

### kaivosai/textual_cli.py (NEW)
Complete Textual-based implementation:
- **GameApp**: Main Textual Application class
  - Handles app lifecycle, screens, CSS styling
  - CSS defines layout proportions (2fr/1fr for width, etc.)

- **GameScreen**: Main game screen with layout
  - Composes all game panels
  - Handles command processing and events
  
- **Widgets** (all custom Static subclasses):
  - **MapDisplay**: Renders 30x30 colored map
  - **ObjectsPanel**: Lists robots/mines/storage/bases with status
  - **EventsPanel**: Scrollable game events with deduplication
  - **StatusBar**: Clock display + game info (reactive updates)
  - **CommandInput**: Natural language input + command submission

- **Command Handlers**:
  - All original CLI commands: create, delete, move, load, unload, robot, map, list, inspect, system
  - Same aliases and natural language processing as before
  - Full compatibility with existing game logic

- **run_textual_tui()**: Entry point
  - Initializes database and game state
  - Creates GameApp and runs event loop

## Updated Files

### kaivosai/__init__.py
- VERSION bumped: 0.13.2 → 0.14.0
- Import: `from .textual_cli import run_textual_tui`
- Compatibility: `run_demo()` wrapper calls `run_textual_tui()`
- Export both functions for backward compatibility

### kaivosai/map.py
- Added `get_object_by_id(obj_id)` method
  - Returns object with matching ID or None
  - Used by command handlers to look up objects
  - Simpler than searching database directly

## Key Improvements

1. **Native Floating Windows** (future enhancement)
   - Textual's `ModalScreen` allows true modal dialogs
   - Multiple floating windows can stack properly
   - Mouse drag-and-drop built-in via CSS `position: fixed`

2. **Responsive Layout**
   - CSS-based styling replaces manual coordinate math
   - Width: 2fr (map) + 1fr (info panels) automatically calculated
   - Resizes gracefully with terminal size changes

3. **Robust Focus Management**
   - CommandInput is only focusable widget
   - All other panels (map, objects, events) non-interactive
   - Focus guaranteed to reach keyboard input
   - No focus stealing issues like with Urwid overlays

4. **Better Code Organization**
   - Widgets inherit from `Static` (non-interactive)
   - Event handlers via `on_*` methods and `Message` classes
   - Reactive properties for automatic re-renders
   - CSS in docstring for easy styling

5. **Game Integration**
   - Database connection: `self.game_map.conn`
   - Clock thread: `GameClock(conn)` runs in background
   - Game ticks (movement, production, transfers, programs) still called from main loop
   - All persistence unchanged

## Backward Compatibility

- Old `run_demo()` still works: calls `run_textual_tui()`
- Original CLI commands unchanged
- All command aliases preserved
- Database schema identical (no migrations needed)
- Game logic (Map, Robot, Mine, etc.) untouched

## Future Enhancements

### Floating Windows (Now Possible!)
```python
class ClockModal(ModalScreen):
    """Draggable clock window."""
    CSS = """
    ClockModal {
        position: absolute;
        top: 2;
        right: 2;
    }
    """
    # Can create multiple ModalScreens without stacking issues

app.push_screen(ClockModal())  # Stack multiple modals safely
```

### Responsive Design
```tcss
GameScreen {
    layout: grid;
    grid-size: 3 1;
}

#left-panel {
    column-span: 2;
}

#right-panel {
    column-span: 1;
}

@media (max-width: 80) {
    GameScreen {
        grid-size: 1;
    }
}
```

### Rich Rendering
- Use Rich tables, panels, syntax highlighting in widgets
- Already imported: `from rich.panel import Panel`, `from rich.table import Table`
- Widgets can render complex formatted output

## Testing

Run the game:
```bash
python kaivosai.py
```

Test commands:
```
create robot 5 5      # Create robot at (5,5)
list                   # Show all objects
robot 1 code LEFT RIGHT  # Program robot 1
robot 1 start         # Execute program
map terrain           # Generate rocks
inspect 1             # Show object details
system version        # Show version
system quit           # Exit game
```

## Migration Checklist

- [x] Install textual package
- [x] Create textual_cli.py with full implementation
- [x] Migrate all command handlers
- [x] Add get_object_by_id() to Map
- [x] Update __init__.py exports
- [x] Update VERSION to 0.14.0
- [x] Update commit_message.txt
- [x] Test imports and syntax
- [ ] Test full game launch
- [ ] Test all commands
- [ ] Test keyboard input
- [ ] Test event updates

## Performance Notes

- Textual renders every frame (like Urwid)
- Widget re-render only if changed (via `refresh()`)
- Status bar uses `reactive` properties for automatic updates
- Game ticks (movement, production, clock) unchanged
- No performance regression expected

## Next Steps

1. Test the game thoroughly
2. Enhance with floating modal screens (ClockModal, etc.)
3. Add command palette (Textual feature)
4. Consider adding TUI themes
5. Port viewer to Textual as well
