import kaivosai
conn = kaivosai.get_game_conn()
rows = kaivosai.load_objects_from_db(conn)
print(f"{len(rows)} rows in DB:\n")
for r in rows:
    print(dict(r))
conn.close()
