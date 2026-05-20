import sqlite3
c = sqlite3.connect('data/papers.db')
rows = c.execute('SELECT tier, COUNT(*), MIN(similarity_score), MAX(similarity_score) FROM papers WHERE seen_date = date(''now'') GROUP BY tier').fetchall()
print(rows)
