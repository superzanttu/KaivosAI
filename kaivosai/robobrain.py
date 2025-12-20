"""RoboBRAIN - RoboBASIC Interpreter and Virtual Machine

Executes RoboBASIC programs for autonomous robot control.
See robot_programming_syntax.txt for complete language specification.
"""

import re
from typing import Dict, List, Tuple, Optional, Any


class SyntaxError(Exception):
    """RoboBASIC syntax error with line number."""
    def __init__(self, line_num: int, message: str):
        self.line_num = line_num
        self.message = message
        super().__init__(f"Line {line_num}: {message}")


class RoboBASICParser:
    """Parse and validate RoboBASIC programs."""
    
    # Command patterns (max 20 chars per line)
    MAX_LINE_LENGTH = 20
    MAX_LABEL_LENGTH = 10
    MAX_MESSAGE_LENGTH = 8
    
    # Valid command keywords
    MOVEMENT_KEYWORDS = {'GOTO', 'UP', 'U', 'DOWN', 'D', 'LEFT', 'L', 'RIGHT', 'R'}
    TRANSFER_KEYWORDS = {'LOAD', 'UNLOAD'}
    CONTROL_KEYWORDS = {'IF', 'NOT', 'FULL', 'EMPTY', 'NEAR', 'RANGE', 'MSG', 'WAIT', 'END', 'STOP'}
    MESSAGING_KEYWORDS = {'SEND', 'CLEAR'}
    PROXIMITY_TYPES = {'SRC', 'DST', 'MINE', 'STORE', 'BASE', 'ROBOT', 'ANY'}
    MESSAGE_TYPES = {'ROBOT', 'MINE', 'STORE', 'BASE', 'ROBOTS', 'MINES', 'STORES', 'BASES'}
    DIRECTIONS = {'U', 'D', 'L', 'R'}
    COUNTS = {'0', '1', 'MANY'}
    
    @staticmethod
    def parse_program(lines: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[str]]:
        """Parse RoboBASIC program and return `(parsed_lines, labels, errors)`.

        Args:
            lines: Program lines (max 20 characters each). May include optional
                labels prefixed with ':' and commands in upper/lower case.

        Returns:
            - parsed_lines: List of dicts `{line_num, label, command, args}` for
              each input line (command is `None` for empty/label-only lines).
            - labels: Mapping of label names to line numbers for jumps.
            - errors: All syntax errors collected (non-fatal) during parsing.

        Note:
            - Empty lines are preserved as no-op entries.
            - Duplicate labels and undefined label references are reported.
            - Line length, label format, and command shapes are validated.
        """
        parsed_lines = []
        labels = {}
        errors = []
        
        for line_num, line in enumerate(lines, start=1):
            # Skip empty lines
            if not line or not line.strip():
                parsed_lines.append({'line_num': line_num, 'label': None, 'command': None, 'args': []})
                continue
            
            # Check line length
            if len(line) > RoboBASICParser.MAX_LINE_LENGTH:
                errors.append(f"Line {line_num}: Too long ({len(line)} > {RoboBASICParser.MAX_LINE_LENGTH} chars)")
                parsed_lines.append({'line_num': line_num, 'label': None, 'command': None, 'args': []})
                continue
            
            # Parse label and command
            label = None
            command_text = line.strip()
            
            # Check for label (starts with :)
            if command_text.startswith(':'):
                # Extract label
                parts = command_text.split(None, 1)
                label_part = parts[0]
                label = label_part[1:]  # Remove leading :
                
                # Validate label
                if not label:
                    errors.append(f"Line {line_num}: Empty label")
                elif len(label) > RoboBASICParser.MAX_LABEL_LENGTH:
                    errors.append(f"Line {line_num}: Label too long ({len(label)} > {RoboBASICParser.MAX_LABEL_LENGTH})")
                elif not re.match(r'^[A-Z0-9]+$', label):
                    errors.append(f"Line {line_num}: Invalid label '{label}' (use A-Z, 0-9 only)")
                else:
                    # Store label
                    if label in labels:
                        errors.append(f"Line {line_num}: Duplicate label '{label}' (first defined on line {labels[label]})")
                    else:
                        labels[label] = line_num
                
                # Get command after label
                command_text = parts[1] if len(parts) > 1 else ''
            
            # Parse command if present
            if command_text:
                try:
                    cmd, args = RoboBASICParser._parse_command(command_text, line_num)
                    parsed_lines.append({'line_num': line_num, 'label': label, 'command': cmd, 'args': args})
                except SyntaxError as e:
                    errors.append(str(e))
                    parsed_lines.append({'line_num': line_num, 'label': label, 'command': None, 'args': []})
            else:
                # Label-only line
                parsed_lines.append({'line_num': line_num, 'label': label, 'command': None, 'args': []})
        
        # Validate label references in GOTO/IF commands
        for parsed in parsed_lines:
            if parsed['command'] in ('GOTO', 'IF'):
                # Check if target label exists
                for arg in parsed['args']:
                    if isinstance(arg, str) and arg.startswith(':'):
                        target_label = arg[1:]
                        if target_label not in labels:
                            errors.append(f"Line {parsed['line_num']}: Undefined label '{target_label}'")
        
        return parsed_lines, labels, errors
    
    @staticmethod
    def _parse_command(command_text: str, line_num: int) -> Tuple[str, List[Any]]:
        """Parse a single command and return `(command_name, args)`.

        Args:
            command_text: Command text (e.g., `GOTO 5 7 D 2`).
            line_num: 1-based line number used for error reporting.

        Returns:
            Tuple containing normalized command name and its argument list.

        Raises:
            SyntaxError: If the command is unknown or has invalid arguments.
        """
        tokens = command_text.upper().split()
        
        if not tokens:
            return 'NOP', []
        
        cmd = tokens[0]
        
        # GOTO X Y [D N] | GOTO ID [D N] | GOTO :LABEL
        if cmd == 'GOTO':
            if len(tokens) < 2:
                raise SyntaxError(line_num, "GOTO requires target")
            
            # Check if target is label
            if tokens[1].startswith(':'):
                return 'GOTO', [tokens[1]]
            
            # Check if coordinates or object ID
            try:
                x = int(tokens[1])
                if len(tokens) >= 3 and not tokens[2] in ('D', 'DIST', 'DISTANCE'):
                    # Two numbers: coordinates
                    y = int(tokens[2])
                    # Check for distance parameter
                    distance = 0
                    if len(tokens) >= 5 and tokens[3] in ('D', 'DIST', 'DISTANCE'):
                        distance = int(tokens[4])
                    return 'GOTO', [('coords', x, y, distance)]
                else:
                    # Single number: object ID
                    distance = 0
                    if len(tokens) >= 4 and tokens[2] in ('D', 'DIST', 'DISTANCE'):
                        distance = int(tokens[3])
                    return 'GOTO', [('object', x, distance)]
            except ValueError:
                raise SyntaxError(line_num, f"Invalid GOTO target: {tokens[1]}")
        
        # Directional movement: UP/DOWN/LEFT/RIGHT N
        if cmd in ('UP', 'U', 'DOWN', 'D', 'LEFT', 'L', 'RIGHT', 'R'):
            if len(tokens) < 2:
                raise SyntaxError(line_num, f"{cmd} requires distance")
            try:
                distance = int(tokens[1])
                return cmd, [distance]
            except ValueError:
                raise SyntaxError(line_num, f"Invalid distance: {tokens[1]}")
        
        # LOAD [N] | UNLOAD [N]
        if cmd in ('LOAD', 'UNLOAD'):
            amount = None
            if len(tokens) >= 2:
                try:
                    amount = int(tokens[1])
                except ValueError:
                    raise SyntaxError(line_num, f"Invalid amount: {tokens[1]}")
            return cmd, [amount] if amount is not None else []
        
        # IF [NOT] condition :label
        if cmd == 'IF':
            return RoboBASICParser._parse_if_command(tokens, line_num)
        
        # SEND TYPE MSG
        if cmd == 'SEND':
            if len(tokens) < 3:
                raise SyntaxError(line_num, "SEND requires TYPE and MESSAGE")
            msg_type = tokens[1]
            message = tokens[2]
            if msg_type not in RoboBASICParser.MESSAGE_TYPES:
                raise SyntaxError(line_num, f"Invalid message type: {msg_type}")
            if len(message) > RoboBASICParser.MAX_MESSAGE_LENGTH:
                raise SyntaxError(line_num, f"Message too long ({len(message)} > {RoboBASICParser.MAX_MESSAGE_LENGTH})")
            return 'SEND', [msg_type, message]
        
        # CLEAR
        if cmd == 'CLEAR':
            return 'CLEAR', []
        
        # WAIT N
        if cmd == 'WAIT':
            if len(tokens) < 2:
                raise SyntaxError(line_num, "WAIT requires duration")
            try:
                duration = int(tokens[1])
                return 'WAIT', [duration]
            except ValueError:
                raise SyntaxError(line_num, f"Invalid duration: {tokens[1]}")
        
        # END | STOP
        if cmd in ('END', 'STOP'):
            return 'END', []
        
        # Unknown command
        raise SyntaxError(line_num, f"Unknown command: {cmd}")
    
    @staticmethod
    def _parse_if_command(tokens: List[str], line_num: int) -> Tuple[str, List[Any]]:
        """Parse `IF [NOT] <condition> :label` command.

        Args:
            tokens: Uppercased token list for the IF command.
            line_num: 1-based line number used for error reporting.

        Returns:
            Normalized `('IF', args)` where `args` encodes condition shape.

        Raises:
            SyntaxError: For missing parts, invalid condition types, or label.
        """
        if len(tokens) < 3:
            raise SyntaxError(line_num, "IF requires condition and label")
        
        idx = 1
        negated = False
        
        # Check for NOT
        if tokens[idx] == 'NOT':
            negated = True
            idx += 1
        
        if idx >= len(tokens):
            raise SyntaxError(line_num, "IF requires condition")
        
        condition_type = tokens[idx]
        idx += 1
        
        # IF [NOT] FULL :label
        if condition_type == 'FULL':
            if idx >= len(tokens) or not tokens[idx].startswith(':'):
                raise SyntaxError(line_num, "IF FULL requires label")
            return 'IF', [negated, 'FULL', tokens[idx]]
        
        # IF [NOT] EMPTY :label
        if condition_type == 'EMPTY':
            if idx >= len(tokens) or not tokens[idx].startswith(':'):
                raise SyntaxError(line_num, "IF EMPTY requires label")
            return 'IF', [negated, 'EMPTY', tokens[idx]]
        
        # IF [NOT] NEAR [count] type :label
        if condition_type == 'NEAR':
            if idx >= len(tokens):
                raise SyntaxError(line_num, "IF NEAR requires type")
            
            # Check for count (0, 1, MANY)
            count = '1'  # Default
            if tokens[idx] in RoboBASICParser.COUNTS:
                count = tokens[idx]
                idx += 1
            
            if idx >= len(tokens):
                raise SyntaxError(line_num, "IF NEAR requires type")
            
            prox_type = tokens[idx]
            idx += 1
            
            if prox_type not in RoboBASICParser.PROXIMITY_TYPES:
                raise SyntaxError(line_num, f"Invalid proximity type: {prox_type}")
            
            if idx >= len(tokens) or not tokens[idx].startswith(':'):
                raise SyntaxError(line_num, "IF NEAR requires label")
            
            return 'IF', [negated, 'NEAR', count, prox_type, tokens[idx]]
        
        # IF [NOT] dir dist type :label (directional scan)
        if condition_type in RoboBASICParser.DIRECTIONS:
            if idx >= len(tokens):
                raise SyntaxError(line_num, f"IF {condition_type} requires distance")
            
            try:
                distance = int(tokens[idx])
                idx += 1
            except ValueError:
                raise SyntaxError(line_num, f"Invalid distance: {tokens[idx]}")
            
            if idx >= len(tokens):
                raise SyntaxError(line_num, f"IF {condition_type} requires type")
            
            scan_type = tokens[idx]
            idx += 1
            
            if scan_type not in RoboBASICParser.PROXIMITY_TYPES:
                raise SyntaxError(line_num, f"Invalid scan type: {scan_type}")
            
            if idx >= len(tokens) or not tokens[idx].startswith(':'):
                raise SyntaxError(line_num, f"IF {condition_type} requires label")
            
            return 'IF', [negated, 'SCAN', condition_type, distance, scan_type, tokens[idx]]
        
        # IF [NOT] RANGE dist type :label
        if condition_type == 'RANGE':
            if idx >= len(tokens):
                raise SyntaxError(line_num, "IF RANGE requires distance")
            
            try:
                distance = int(tokens[idx])
                idx += 1
            except ValueError:
                raise SyntaxError(line_num, f"Invalid distance: {tokens[idx]}")
            
            if idx >= len(tokens):
                raise SyntaxError(line_num, "IF RANGE requires type")
            
            range_type = tokens[idx]
            idx += 1
            
            if range_type not in RoboBASICParser.PROXIMITY_TYPES:
                raise SyntaxError(line_num, f"Invalid range type: {range_type}")
            
            if idx >= len(tokens) or not tokens[idx].startswith(':'):
                raise SyntaxError(line_num, "IF RANGE requires label")
            
            return 'IF', [negated, 'RANGE', distance, range_type, tokens[idx]]
        
        # IF [NOT] MSG type message :label
        if condition_type == 'MSG':
            if idx + 2 >= len(tokens):
                raise SyntaxError(line_num, "IF MSG requires type, message, and label")
            
            msg_type = tokens[idx]
            message = tokens[idx + 1]
            label = tokens[idx + 2]
            
            if msg_type not in RoboBASICParser.MESSAGE_TYPES:
                raise SyntaxError(line_num, f"Invalid message type: {msg_type}")
            
            if not label.startswith(':'):
                raise SyntaxError(line_num, "IF MSG requires label")
            
            return 'IF', [negated, 'MSG', msg_type, message, label]
        
        raise SyntaxError(line_num, f"Invalid IF condition: {condition_type}")


class RoboBRAINExecutor:
    """Execute RoboBASIC programs for robots."""
    
    @staticmethod
    def execute_next_line(robot, game_map, game_seconds: int) -> Optional[str]:
        """Execute one line of a robot's program.

        Args:
            robot: Robot instance containing program state and runtime fields.
            game_map: `Map` providing spatial queries and actions.
            game_seconds: Current game time in seconds (for WAIT and MSG).

        Returns:
            Status message string for terminal events (END, errors), or `None`
            when execution continues normally.

        Note:
            - Skips empty lines and advances `_program_counter` appropriately.
            - Stops program on runtime errors, returning a descriptive message.
            - Movement and transfer operations set state and advance counter.
        """
        # Check if blocked (WAIT or movement)
        if robot._blocked_until > game_seconds:
            return None  # Still blocked
        
        # Check if program is running
        if not robot._program_running:
            return "Program not running"
        
        # Check if program counter is valid
        if robot._program_counter >= len(robot._parsed_program):
            robot._program_running = False
            return "Program ended (reached end)"
        
        # Get current line
        line = robot._parsed_program[robot._program_counter]
        
        # Skip empty lines
        if line['command'] is None:
            robot._program_counter += 1
            return None
        
        cmd = line['command']
        args = line['args']
        
        try:
            # Execute command
            if cmd == 'GOTO':
                return RoboBRAINExecutor._execute_goto(robot, args, game_map)
            elif cmd in ('UP', 'U', 'DOWN', 'D', 'LEFT', 'L', 'RIGHT', 'R'):
                return RoboBRAINExecutor._execute_direction(robot, cmd, args, game_map)
            elif cmd == 'LOAD':
                return RoboBRAINExecutor._execute_load(robot, args, game_map)
            elif cmd == 'UNLOAD':
                return RoboBRAINExecutor._execute_unload(robot, args, game_map)
            elif cmd == 'IF':
                return RoboBRAINExecutor._execute_if(robot, args, game_map, game_seconds)
            elif cmd == 'SEND':
                return RoboBRAINExecutor._execute_send(robot, args, game_map, game_seconds)
            elif cmd == 'CLEAR':
                robot._message_inbox = []
                robot._program_counter += 1
                return None
            elif cmd == 'WAIT':
                robot._blocked_until = game_seconds + args[0]
                robot._program_counter += 1
                return None
            elif cmd == 'END':
                robot._program_running = False
                return "Program ended (END command)"
            else:
                robot._program_counter += 1
                return f"Unknown command: {cmd}"
        except Exception as e:
            robot._program_running = False
            return f"Runtime error on line {robot._program_counter + 1}: {e}"
    
    @staticmethod
    def _execute_goto(robot, args, game_map):
        """Execute `GOTO` command.

        Supports label jumps (`GOTO :LABEL`), coordinates, and object-ID
        targets with optional stop distance via `D|DIST|DISTANCE N`.
        """
        if not args:
            robot._program_counter += 1
            return "GOTO: No target"
        
        target = args[0]
        
        # GOTO :LABEL
        if isinstance(target, str) and target.startswith(':'):
            label_name = target[1:]
            if label_name in robot._program_labels:
                robot._program_counter = robot._program_labels[label_name] - 1  # -1 because we increment after
                return None
            else:
                robot._program_running = False
                return f"Undefined label: {label_name}"
        
        # GOTO coords or object
        if isinstance(target, tuple):
            if target[0] == 'coords':
                _, x, y, distance = target
                try:
                    game_map.command_move_robot(robot.id, (x, y), distance)
                    robot._program_counter += 1
                    # Block until movement completes (movement system handles this)
                    return None
                except Exception as e:
                    robot._program_counter += 1
                    return f"GOTO error: {e}"
            elif target[0] == 'object':
                _, obj_id, distance = target
                # Find object
                target_obj = None
                for obj in game_map.cells.values():
                    if getattr(obj, 'id', None) == obj_id:
                        target_obj = obj
                        break
                
                if not target_obj:
                    robot._program_counter += 1
                    return f"Object {obj_id} not found"
                
                try:
                    x, y = target_obj.pos
                    # Default: adjacent (1 cell away) if no distance
                    stop_dist = distance if distance > 0 else 1
                    game_map.command_move_robot(robot.id, (x, y), stop_dist)
                    robot._program_counter += 1
                    return None
                except Exception as e:
                    robot._program_counter += 1
                    return f"GOTO error: {e}"
        
        robot._program_counter += 1
        return "GOTO: Invalid target"
    
    @staticmethod
    def _execute_direction(robot, cmd, args, game_map):
        """Execute directional movement (`UP|DOWN|LEFT|RIGHT N`).

        Computes target by offsetting current position with `N` steps and
        delegates actual pathfinding movement to `Map.command_move_robot()`.
        """
        if not args:
            robot._program_counter += 1
            return f"{cmd}: No distance"
        
        distance = args[0]
        x, y = robot.pos
        
        # Calculate target position
        if cmd in ('UP', 'U'):
            target = (x, y - distance)
        elif cmd in ('DOWN', 'D'):
            target = (x, y + distance)
        elif cmd in ('LEFT', 'L'):
            target = (x - distance, y)
        elif cmd in ('RIGHT', 'R'):
            target = (x + distance, y)
        else:
            robot._program_counter += 1
            return f"Unknown direction: {cmd}"
        
        try:
            game_map.command_move_robot(robot.id, target, 0)
            robot._program_counter += 1
            return None
        except Exception as e:
            robot._program_counter += 1
            return f"{cmd} error: {e}"
    
    @staticmethod
    def _execute_load(robot, args, game_map):
        """Execute `LOAD [N]` command.

        Starts incremental loading (1/s) from a single adjacent source
        (Mine/Storage/Base/Robot). If multiple sources or none are found,
        the command is skipped.
        """
        amount = args[0] if args else None
        
        # Get adjacent objects
        adjacent = game_map.get_adjacent_objects(robot.pos)
        from .models import Mine, Storage, Base, Robot as RobotClass
        
        # Filter valid sources
        sources = [obj for obj in adjacent if isinstance(obj, (Mine, Storage, Base, RobotClass)) and obj != robot]
        sources = [obj for obj in sources if hasattr(obj, 'stored') and obj.stored > 0 or 
                   (isinstance(obj, RobotClass) and obj.inventory > 0)]
        
        if not sources:
            robot._program_counter += 1
            return None  # No source available, continue
        
        if len(sources) > 1:
            robot._program_counter += 1
            return None  # Multiple sources, skip (could be error in real impl)
        
        source = sources[0]
        robot.start_loading(source, amount)
        robot._program_counter += 1
        return None
    
    @staticmethod
    def _execute_unload(robot, args, game_map):
        """Execute `UNLOAD [N]` command.

        Starts incremental unloading (1/s) to a single adjacent destination
        (Storage/Base/Robot). If multiple destinations or none are found,
        the command is skipped.
        """
        amount = args[0] if args else None
        
        # Get adjacent objects
        adjacent = game_map.get_adjacent_objects(robot.pos)
        from .models import Storage, Base, Robot as RobotClass
        
        # Filter valid destinations
        dests = [obj for obj in adjacent if isinstance(obj, (Storage, Base, RobotClass)) and obj != robot]
        
        if not dests:
            robot._program_counter += 1
            return None  # No destination, continue
        
        if len(dests) > 1:
            robot._program_counter += 1
            return None  # Multiple destinations, skip
        
        dest = dests[0]
        robot.start_unloading(dest, amount)
        robot._program_counter += 1
        return None
    
    @staticmethod
    def _execute_if(robot, args, game_map, game_seconds):
        """Execute `IF` command.

        Evaluates conditions: `FULL`, `EMPTY`, `NEAR`, directional `SCAN`,
        `RANGE`, and `MSG`. Applies optional `NOT`. On true, jumps to label;
        otherwise advances program counter.
        """
        negated = args[0]
        condition_type = args[1]
        
        result = False
        
        if condition_type == 'FULL':
            result = robot.inventory >= robot.capacity
        elif condition_type == 'EMPTY':
            result = robot.inventory == 0
        elif condition_type == 'NEAR':
            count = args[2]
            prox_type = args[3]
            label = args[4]
            result = RoboBRAINExecutor._check_proximity(robot, count, prox_type, game_map)
        elif condition_type == 'SCAN':
            direction = args[2]
            distance = args[3]
            scan_type = args[4]
            label = args[5]
            result = RoboBRAINExecutor._check_directional_scan(robot, direction, distance, scan_type, game_map)
        elif condition_type == 'RANGE':
            distance = args[2]
            range_type = args[3]
            label = args[4]
            result = RoboBRAINExecutor._check_range(robot, distance, range_type, game_map)
        elif condition_type == 'MSG':
            msg_type = args[2]
            message = args[3]
            label = args[4]
            result = RoboBRAINExecutor._check_message(robot, msg_type, message, game_seconds)
        
        # Apply negation
        if negated:
            result = not result
        
        # Jump if condition is true
        if result:
            # Get label from args
            if condition_type in ('FULL', 'EMPTY'):
                label = args[2]
            elif condition_type in ('NEAR', 'RANGE'):
                label = args[4]
            elif condition_type == 'SCAN':
                label = args[5]
            elif condition_type == 'MSG':
                label = args[4]
            
            label_name = label[1:]  # Remove :
            if label_name in robot._program_labels:
                robot._program_counter = robot._program_labels[label_name] - 1
            else:
                robot._program_running = False
                return f"Undefined label: {label_name}"
        else:
            robot._program_counter += 1
        
        return None
    
    @staticmethod
    def _check_proximity(robot, count, prox_type, game_map):
        """Check adjacent objects for `NEAR` condition.

        Args:
            count: One of `'0'|'1'|'MANY'`.
            prox_type: `'SRC'|'DST'|'MINE'|'STORE'|'BASE'|'ROBOT'|'ANY'`.
            game_map: `Map` instance for queries.

        Returns:
            True if adjacency matches the desired count and type.
        """
        adjacent = game_map.get_adjacent_objects(robot.pos)
        from .models import Mine, Storage, Base, Robot as RobotClass
        
        # Filter by type
        if prox_type == 'SRC':
            # Sources: Mine, Storage, Base with stored > 0
            matches = [obj for obj in adjacent if isinstance(obj, (Mine, Storage, Base)) and 
                      hasattr(obj, 'stored') and obj.stored > 0]
        elif prox_type == 'DST':
            # Destinations: Storage, Base not full
            matches = [obj for obj in adjacent if isinstance(obj, (Storage, Base)) and
                      hasattr(obj, 'stored') and hasattr(obj, 'capacity') and obj.stored < obj.capacity]
        elif prox_type == 'MINE':
            matches = [obj for obj in adjacent if isinstance(obj, Mine)]
        elif prox_type == 'STORE':
            matches = [obj for obj in adjacent if isinstance(obj, Storage)]
        elif prox_type == 'BASE':
            matches = [obj for obj in adjacent if isinstance(obj, Base)]
        elif prox_type == 'ROBOT':
            matches = [obj for obj in adjacent if isinstance(obj, RobotClass) and obj != robot]
        elif prox_type == 'ANY':
            matches = adjacent
        else:
            matches = []
        
        # Check count
        actual_count = len(matches)
        if count == '0':
            return actual_count == 0
        elif count == '1':
            return actual_count == 1
        elif count == 'MANY':
            return actual_count >= 2
        
        return False
    
    @staticmethod
    def _check_directional_scan(robot, direction, distance, scan_type, game_map):
        """Check presence at exact distance along a direction (`SCAN`).

        Args:
            direction: `'U'|'D'|'L'|'R'`.
            distance: Positive integer steps.
            scan_type: Object type filter (incl. `'ANY'`, `'SRC'`, `'DST'`).
            game_map: `Map` instance.

        Returns:
            True if an object of matching type exists exactly at the target.
        """
        x, y = robot.pos
        
        # Calculate target position
        if direction == 'U':
            target = (x, y - distance)
        elif direction == 'D':
            target = (x, y + distance)
        elif direction == 'L':
            target = (x - distance, y)
        elif direction == 'R':
            target = (x + distance, y)
        else:
            return False
        
        # Check if position is valid
        if not game_map.in_bounds(target):
            return False
        
        # Get object at position
        obj = game_map.get(target)
        if not obj:
            return False
        
        # Check type
        from .models import Mine, Storage, Base, Robot as RobotClass, Rock
        
        if scan_type == 'ANY':
            return True
        elif scan_type == 'MINE':
            return isinstance(obj, Mine)
        elif scan_type == 'STORE':
            return isinstance(obj, Storage)
        elif scan_type == 'BASE':
            return isinstance(obj, Base)
        elif scan_type == 'ROBOT':
            return isinstance(obj, RobotClass)
        elif scan_type == 'SRC':
            return isinstance(obj, (Mine, Storage, Base)) and hasattr(obj, 'stored') and obj.stored > 0
        elif scan_type == 'DST':
            return isinstance(obj, (Storage, Base)) and hasattr(obj, 'stored') and hasattr(obj, 'capacity') and obj.stored < obj.capacity
        
        return False
    
    @staticmethod
    def _check_range(robot, distance, range_type, game_map):
        """Check for objects within Manhattan distance (`RANGE`).

        Args:
            distance: Inclusive Manhattan radius.
            range_type: Object type filter (incl. `'ANY'`, `'SRC'`, `'DST'`).
            game_map: `Map` instance.

        Returns:
            True if any matching object is found within the radius.
        """
        x, y = robot.pos
        from .models import Mine, Storage, Base, Robot as RobotClass
        
        # Scan area
        for dx in range(-distance, distance + 1):
            for dy in range(-distance, distance + 1):
                # Manhattan distance
                if abs(dx) + abs(dy) > distance:
                    continue
                
                target = (x + dx, y + dy)
                if not game_map.in_bounds(target):
                    continue
                
                obj = game_map.get(target)
                if not obj or target == robot.pos:
                    continue
                
                # Check type
                if range_type == 'ANY':
                    return True
                elif range_type == 'MINE' and isinstance(obj, Mine):
                    return True
                elif range_type == 'STORE' and isinstance(obj, Storage):
                    return True
                elif range_type == 'BASE' and isinstance(obj, Base):
                    return True
                elif range_type == 'ROBOT' and isinstance(obj, RobotClass):
                    return True
                elif range_type == 'SRC' and isinstance(obj, (Mine, Storage, Base)) and hasattr(obj, 'stored') and obj.stored > 0:
                    return True
                elif range_type == 'DST' and isinstance(obj, (Storage, Base)) and hasattr(obj, 'stored') and hasattr(obj, 'capacity') and obj.stored < obj.capacity:
                    return True
        
        return False
    
    @staticmethod
    def _check_message(robot, msg_type, message, game_seconds):
        """Check inbox for a non-expired message (`MSG`).

        Args:
            msg_type: Message type filter (e.g., `'ROBOT'`).
            message: Message payload (<= 8 chars).
            game_seconds: Current time used for expiry (3600s window).

        Returns:
            True if a matching, non-expired message is consumed.
        """
        # Message format: (sender_type, message, timestamp)
        # Check if any message matches and hasn't expired (3600 seconds = 1 hour)
        for sender_type, msg, timestamp in robot._message_inbox:
            if game_seconds - timestamp > 3600:
                continue  # Expired
            if sender_type == msg_type and msg == message:
                # Consume message
                robot._message_inbox.remove((sender_type, msg, timestamp))
                return True
        
        return False
    
    @staticmethod
    def _execute_send(robot, args, game_map, game_seconds):
        """Execute `SEND TYPE MSG` - broadcast message to objects of type.

        Args:
            robot: Sender robot.
            args: `[msg_type, message]`.
            game_map: `Map` instance to enumerate recipients.
            game_seconds: Timestamp for inbox entries.

        Returns:
            None. Advances program counter after enqueueing messages.
        """
        msg_type = args[0]
        message = args[1]
        
        from .models import Mine, Storage, Base, Robot as RobotClass
        
        # Determine sender type
        sender_type = 'ROBOT'
        
        # Get target objects based on type
        targets = []
        for obj in game_map.cells.values():
            if msg_type == 'ROBOTS' and isinstance(obj, RobotClass):
                targets.append(obj)
            elif msg_type == 'MINES' and isinstance(obj, Mine):
                targets.append(obj)
            elif msg_type == 'STORES' and isinstance(obj, Storage):
                targets.append(obj)
            elif msg_type == 'BASES' and isinstance(obj, Base):
                targets.append(obj)
        
        # Send message to all targets
        for target in targets:
            if not hasattr(target, '_message_inbox'):
                target._message_inbox = []
            target._message_inbox.append((sender_type, message, game_seconds))
        
        robot._program_counter += 1
        return None

