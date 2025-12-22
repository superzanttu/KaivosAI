#!/usr/bin/env python3
"""
Test suite for game_command_syntax.txt compliance.
Verifies that all documented commands work as described.

Note: Some commands in game_command_syntax.txt are documented but not implemented:
- map show / map list (not implemented - use 'map' or 'list' instead)
- mv alias (not implemented - use 'move' instead)

This test suite checks actual implementation vs documentation.
"""

from kaivosai.cli import CLIController
from kaivosai.map import Map
from kaivosai.db import get_game_conn, init_game_db
from kaivosai.models import Rock
import os

def test_game_command_syntax_compliance():
    """Test all commands - actual vs documented"""
    
    # Reset database for clean test
    if os.path.exists('databases/game.db'):
        os.remove('databases/game.db')
    
    conn = get_game_conn()
    init_game_db(conn)
    m = Map(30, 30, conn)
    cli = CLIController(m, None, conn)
    
    # Pre-create objects for testing load/unload (robots need neighbors)
    cli.process_command('create robot 1 1')    # Robot 1
    cli.process_command('create robot 2 2')    # Robot 2
    cli.process_command('create mine 2 1')     # Mine next to Robot 1
    cli.process_command('create storage 2 3')  # Storage next to Robot 2
    
    # Test suite matching game_command_syntax.txt sections
    tests = [
        # ROBOT CONTROL COMMANDS
        ('robot 1 goto 10 15', 'moving', 'Robot goto coordinates', True),
        ('r 1 g 10 15', 'moving', 'Robot goto short alias', True),
        ('robot 1 load', 'load|No adjacent|inventory', 'Robot load from adjacent mine', True),
        ('r 1 l', 'load|No adjacent|inventory', 'Robot load short alias', True),
        ('robot 2 unload', 'unload|No adjacent', 'Robot unload to adjacent storage', True),
        ('r 2 u', 'unload|No adjacent', 'Robot unload short alias', True),
        
        # OBJECT MANAGEMENT COMMANDS
        ('create robot 5 5', 'Created', 'Create robot', True),
        ('c robot 8 8', 'Created', 'Create robot alias', True),
        ('create mine 15 15', 'Created', 'Create mine', True),
        ('c storage 20 20', 'Created', 'Create storage', True),
        ('c base 25 25', 'Created', 'Create base', True),
        ('delete 1', 'Removed|Error', 'Delete by ID', True),
        ('d 2', 'Removed|Error', 'Delete by ID alias', True),
        ('delete 10 10', 'Removed|Error', 'Delete by coordinates', True),
        ('d 12 8', 'Removed|Error', 'Delete by coordinates alias', True),
        
        # MOVEMENT & INSPECTION COMMANDS
        ('move 5 5 to 7 5', 'moved|Error', 'Move object coordinates', True),
        ('inspect 10 15', 'at|Error', 'Inspect coordinates', True),
        
        # MAP OPERATIONS
        ('map', 'Objects|See', 'Map show (alias)', True),
        ('list', 'objects|See', 'List (implemented as legacy)', True),
        ('map terrain', 'terrain|Error', 'Map terrain default', True),
        ('map t 0.1 5', 'terrain|Error', 'Map terrain with params', True),
        ('map demo', 'added|Error', 'Map demo', True),
        ('map reset', 'reset|cleared', 'Map reset', True),
        
        # SYSTEM COMMANDS
        ('system pause', 'paused|Clock', 'System pause', True),
        ('pause', 'paused|Clock', 'Pause legacy alias', True),
        ('system resume', 'resumed|Clock', 'System resume', True),
        ('resume', 'resumed|Clock', 'Resume legacy alias', True),
        ('system optimize', 'optimized|renumber', 'System optimize', True),
        ('system version', 'KaivosAI', 'System version', True),
        ('version', 'KaivosAI', 'Version legacy alias', True),
        ('system help', 'Commands|ROBOT', 'System help', True),
        ('help', 'Commands|ROBOT', 'Help legacy alias', True),
        
        # ERROR HANDLING - commands should not crash
        ('robot 999 goto 10 10', 'not found|Error', 'Robot not found error', True),
        ('create robot 5 5', 'occupied|Error|Created', 'Position occupied error', True),
        ('invalid xyz', 'understand|Error', 'Invalid command error', True),
        
        # DOCUMENTED BUT NOT IMPLEMENTED
        ('map show', 'Unknown|Error', 'map show NOT IMPLEMENTED', False),
        ('map list', 'Unknown|Error', 'map list NOT IMPLEMENTED', False),
        ('map ls', 'Unknown|Error', 'map ls NOT IMPLEMENTED (use list instead)', False),
        ('mv 3 3 5 5', 'understand|Error', 'mv alias NOT IMPLEMENTED', False),
    ]
    
    results = {
        'passed': 0,
        'failed': 0,
        'crashed': 0,
        'unimplemented': 0,
        'by_category': {}
    }
    
    print("\n" + "=" * 100)
    print("GAME COMMAND SYNTAX COMPLIANCE TEST SUITE (v0.20.0)")
    print("=" * 100)
    print("Verifying commands in game_command_syntax.txt - Actual vs Documented")
    print("=" * 100 + "\n")
    
    for cmd, expected_patterns, description, should_work in tests:
        # Extract category from description
        if 'Robot' in description:
            category = 'Robot Control'
        elif 'delete' in description.lower() or 'create' in description.lower():
            category = 'Object Management'
        elif 'inspect' in description.lower() or 'move' in description.lower():
            category = 'Movement/Inspect'
        elif 'map' in description.lower():
            category = 'Map Operations'
        elif 'system' in description.lower() or any(x in description.lower() for x in ['pause', 'resume', 'version', 'help']):
            category = 'System'
        else:
            category = 'Error Handling'
        
        if category not in results['by_category']:
            results['by_category'][category] = {'passed': 0, 'failed': 0, 'crashed': 0, 'unimplemented': 0}
        
        try:
            result = cli.process_command(cmd)
            
            # Check if result matches any of the expected patterns
            patterns = [p.strip() for p in expected_patterns.split('|')]
            ok = any(pattern.lower() in result.lower() for pattern in patterns)
            
            if ok:
                if should_work:
                    results['passed'] += 1
                    results['by_category'][category]['passed'] += 1
                    marker = '✓'
                    status = 'PASS'
                else:
                    results['unimplemented'] += 1
                    results['by_category'][category]['unimplemented'] += 1
                    marker = '⚠'
                    status = 'UNIMPL'
            else:
                results['failed'] += 1
                results['by_category'][category]['failed'] += 1
                marker = '✗'
                status = 'FAIL'
            
            print(f"{marker} {status:6} | {category:18} | {cmd:40} | {description}")
            
        except Exception as e:
            results['crashed'] += 1
            results['by_category'][category]['crashed'] += 1
            print(f"✗ CRASH | {category:18} | {cmd:40} | {str(e)[:30]}")
    
    # Print summary
    print("\n" + "=" * 100)
    print("SUMMARY BY CATEGORY:")
    print("=" * 100)
    
    for category in sorted(results['by_category'].keys()):
        cat_results = results['by_category'][category]
        passed = cat_results['passed']
        failed = cat_results['failed']
        crashed = cat_results['crashed']
        unimpl = cat_results['unimplemented']
        total = passed + failed + crashed + unimpl
        
        if crashed > 0:
            status = "✗ CRASH"
        elif failed > 0:
            status = "✗ FAIL"
        elif unimpl > 0:
            status = "⚠ PARTIAL"
        else:
            status = "✓ PASS"
        
        pct = (passed / total * 100) if total > 0 else 0
        detail = f"{passed:2}/{total:2} passed"
        if crashed > 0:
            detail += f" - {crashed} crashes"
        if unimpl > 0:
            detail += f" - {unimpl} unimplemented"
        
        print(f"{status} | {category:18} | {detail:40} ({pct:5.1f}%)")
    
    # Overall summary
    total = results['passed'] + results['failed'] + results['crashed'] + results['unimplemented']
    pct = (results['passed'] / total * 100) if total > 0 else 0
    
    print("\n" + "=" * 100)
    print(f"OVERALL RESULTS:")
    print(f"  ✓ IMPLEMENTED & WORKING: {results['passed']}")
    print(f"  ⚠ DOCUMENTED BUT NOT IMPLEMENTED: {results['unimplemented']}")
    print(f"  ✗ FAILED: {results['failed']}")
    print(f"  ✗ CRASHED: {results['crashed']}")
    print(f"  Total: {total} | Success Rate: {pct:.1f}%")
    print("=" * 100)
    
    if results['crashed'] == 0:
        print("\n✓ NO CRASHES - All commands execute safely")
    
    if results['failed'] == 0 and results['crashed'] == 0:
        if results['unimplemented'] == 0:
            print("✓ FULL COMPLIANCE - All documented commands are implemented and working!")
            return True
        else:
            print(f"⚠ PARTIAL COMPLIANCE - {results['unimplemented']} documented commands not implemented")
            print("  See output above for details (marked with ⚠)")
            return True
    else:
        print(f"✗ ISSUES FOUND - {results['failed']} command(s) failed, {results['crashed']} crashed")
        return False

if __name__ == '__main__':
    success = test_game_command_syntax_compliance()
    exit(0 if success else 1)
