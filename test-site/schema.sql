DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS cells;
DROP TABLE IF EXISTS users;
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user','admin','monitor'))
);
CREATE TABLE cells (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'grey' CHECK(status IN ('grey','red','available')),
  opened_at TEXT,
  permanently_unavailable INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_id INTEGER NOT NULL,
  username TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  reserved_at TEXT NOT NULL,
  open_seconds REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE sessions (
  token TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  role TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO users (username,password,role) VALUES
 ('testuser','test123','user'),
 ('admin','admin123','admin'),
 ('monitor','monitor123','monitor');
