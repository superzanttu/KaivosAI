import kaivosai
import mapviewer

conn = kaivosai.get_game_conn()
rows = kaivosai.load_objects_from_db(conn)
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
