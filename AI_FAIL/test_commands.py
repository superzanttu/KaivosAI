#!/usr/bin/env python3
"""Test all commands to verify fixes work"""

from kaivosai.cli import CLIController
from kaivosai.map import Map
from kaivosai.db import get_game_conn, init_game_db
import os

# Reset database
if os.path.exists('databases/game.db'):
    os.remove('databases/game.db')

conn = get_game_conn()
init_game_db(conn)
m = Map(30, 30, conn)
cli = CLIController(m, None, conn)

tests = [
    ('help', 'ROBOT'),
    ('version', 'KaivosAI'),
    ('create robot 5 5', 'Created'),
    ('create storage 10 10', 'Created'),
    ('inspect 5 5', 'Robot'),
    ('move 5 5 to 7 5', 'moved'),
    ('robot 1 goto 8 8', 'moving'),
    ('pause', 'paused'),
    ('resume', 'resumed'),
    ('invalid xyz', 'understand'),
]

passed = 0
failed = 0

print("=" * 70)
print("COMMAND TEST SUITE - KaivosAI v0.20.0")
print("=" * 70)

for cmd, expected in tests:
    try:
        result = cli.process_command(cmd)
        ok = expected.lower() in result.lower()
        
        if ok:
            passed += 1
            marker = '✓ PASS'
        else:
            failed += 1
            marker = '✗ FAIL'
            
        print(f"{marker} | {cmd:30} | {result[:40]}")
    except Exception as e:
        failed += 1
        print(f"✗ CRASH | {cmd:30} | {str(e)[:40]}")

print("=" * 70)
print(f"Results: {passed} PASSED, {failed} FAILED")
print("=" * 70)

if failed == 0:
    print("✓ All tests passed! Commands are working correctly.")
else:
    print(f"✗ {failed} test(s) failed. Check output above.")
