import kaivosai
from kaivosai.map import Map

conn = kaivosai.get_game_conn()
map_obj = Map(width=50, height=50, conn=conn)
# find robot with id=1
robot_pos = None
for p,o in map_obj.cells.items():
    if getattr(o, 'id', None) == 1:
        robot_pos = p
        break
print('Found robot at', robot_pos)
if robot_pos is None:
    print('No robot id=1 found; abort')
else:
    new_pos = (7,5)
    try:
        map_obj.move_object(robot_pos, new_pos)
        print('Moved robot to', new_pos)
    except Exception as e:
        print('Move failed:', e)

# dump DB rows
rows = kaivosai.load_objects_from_db(conn)
print('\nDB rows after move:')
for r in rows:
    print(dict(r))

# run one-shot viewer render
import mapviewer
objs = []
for r in rows:
    try:
        obj = kaivosai.create_object(r['type'], id=r['id'], name=r['name'], pos=(r['x'], r['y']), capacity=r['capacity'], durability=r['durability'])
    except Exception:
        class Simple:
            def __init__(self, pos):
                self.pos = pos
        obj = Simple((r['x'], r['y']))
    objs.append(obj)
minx, maxx, miny, maxy = mapviewer.compute_auto_bounds(objs, 30, 15)
mapviewer.clear_screen()
print(f"Objs: {len(objs)}\nBounds: x={minx}..{maxx} y={miny}..{maxy}\n")
mapviewer.render(objs, minx, maxx, miny, maxy)
conn.close()
