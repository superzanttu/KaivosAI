#!/usr/bin/env python3
"""
Comprehensive test suite for KaivosAI command handling.
Tests the critical bug fix: All commands should work without crashing.
"""

from kaivosai.cli import CLIController
from kaivosai.map import Map
from kaivosai.db import get_game_conn, init_game_db
import os

def test_all_commands():
    """Test all major command categories to verify the bug fix."""
    
    # Reset database for clean test
    if os.path.exists('databases/game.db'):
        os.remove('databases/game.db')
    
    conn = get_game_conn()
    init_game_db(conn)
    m = Map(30, 30, conn)
    cli = CLIController(m, None, conn)
    
    # Test suite: (command, expected_text_in_result, category)
    tests = [
        # System commands
        ('help', 'ROBOT', 'System'),
        ('version', 'KaivosAI', 'System'),
        ('pause', 'paused', 'System'),
        ('resume', 'resumed', 'System'),
        
        # Creation commands
        ('create robot 5 5', 'Created', 'Create'),
        ('create robot 8 8', 'Created', 'Create'),
        ('create mine 15 15', 'Created', 'Create'),
        ('create storage 20 20', 'Created', 'Create'),
        ('create base 25 25', 'Created', 'Create'),
        
        # Map navigation
        ('inspect 5 5', 'Robot', 'Inspect'),
        ('list', 'objects', 'List'),
        
        # Object movement
        ('move 5 5 to 7 5', 'moved', 'Move'),
        
        # Robot commands
        ('robot 1 goto 8 8', 'moving', 'Robot'),
        ('robot 1 goto 2', 'moving', 'Robot'),
        
        # Error handling
        ('invalid xyz', 'understand', 'Error'),
        ('create robot 5 5', 'occupied', 'Error'),  # Cell already occupied
        ('robot 999 goto 10 10', 'not found', 'Error'),  # Non-existent robot
    ]
    
    results = {
        'passed': 0,
        'failed': 0,
        'by_category': {}
    }
    
    print("\n" + "=" * 80)
    print("COMPREHENSIVE COMMAND TEST SUITE - KaivosAI v0.20.0")
    print("=" * 80)
    print("Testing critical bug fix: All commands should work without crashing")
    print("=" * 80 + "\n")
    
    for cmd, expected, category in tests:
        if category not in results['by_category']:
            results['by_category'][category] = {'passed': 0, 'failed': 0}
        
        try:
            result = cli.process_command(cmd)
            ok = expected.lower() in result.lower()
            
            if ok:
                results['passed'] += 1
                results['by_category'][category]['passed'] += 1
                marker = '✓ PASS'
            else:
                results['failed'] += 1
                results['by_category'][category]['failed'] += 1
                marker = '✗ FAIL'
            
            print(f"{marker} {category:10} | {cmd:35} | {result[:45]}")
        except Exception as e:
            results['failed'] += 1
            results['by_category'][category]['failed'] += 1
            print(f"✗ CRASH {category:3} | {cmd:35} | {str(e)[:40]}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY BY CATEGORY:")
    print("=" * 80)
    
    for category in sorted(results['by_category'].keys()):
        cat_results = results['by_category'][category]
        passed = cat_results['passed']
        failed = cat_results['failed']
        total = passed + failed
        status = "✓" if failed == 0 else "✗"
        pct = (passed / total * 100) if total > 0 else 0
        print(f"{status} {category:10} | {passed:2}/{total:2} passed ({pct:5.1f}%)")
    
    # Overall summary
    total = results['passed'] + results['failed']
    pct = (results['passed'] / total * 100) if total > 0 else 0
    
    print("\n" + "=" * 80)
    print(f"OVERALL RESULTS: {results['passed']} PASSED, {results['failed']} FAILED")
    print(f"Success Rate: {pct:.1f}%")
    print("=" * 80)
    
    if results['failed'] == 0:
        print("\n✓ ALL TESTS PASSED!")
        print("✓ The critical bug fix is working correctly.")
        print("✓ All commands execute without crashing the game.")
        return True
    else:
        print(f"\n✗ {results['failed']} test(s) failed.")
        print("✗ Check output above for details.")
        return False

if __name__ == '__main__':
    success = test_all_commands()
    exit(0 if success else 1)
