// Minimal Express API to exercise the database connection, local assets, and TMDB calls.
const express = require("express");
const cors = require("cors");
const path = require("path");
const fs = require("fs").promises;
const { Pool } = require("pg");
require("dotenv").config();

const PORT = process.env.PORT || 8080;

const MOVIE_DATA_ROOT =
  process.env.MOVIE_DATA_ROOT ||
  path.join("/mnt/user/CineGuess/private_data/movie_data");

// Build pool config from DATABASE_URL or discrete PG* env vars.
const poolConfig = process.env.DATABASE_URL
  ? {
      connectionString: process.env.DATABASE_URL,
      ssl:
        process.env.PGSSLMODE === "require"
          ? { rejectUnauthorized: false }
          : false,
    }
  : {
      host: process.env.PGHOST,
      port: process.env.PGPORT,
      user: process.env.PGUSER,
      password: process.env.PGPASSWORD,
      database: process.env.PGDATABASE,
      ssl:
        process.env.PGSSLMODE === "require"
          ? { rejectUnauthorized: false }
          : false,
    };

const pool = new Pool(poolConfig);

const app = express();
app.use(cors());
app.use(express.json());

// Optionally serve private assets if mounted.
app.use("/media", express.static(MOVIE_DATA_ROOT));

app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    uptime_seconds: process.uptime(),
    movie_data_root: MOVIE_DATA_ROOT,
  });
});

app.get("/api/db-check", async (req, res) => {
  try {
    const result = await pool.query("select now() as now, version();");
    res.json({ ok: true, rows: result.rows });
  } catch (err) {
    console.error("db-check error", err);
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get("/api/movies", async (req, res) => {
  try {
    const result = await pool.query(
      "select id, title from movies order by id limit 10;"
    );
    res.json({ ok: true, count: result.rowCount, rows: result.rows });
  } catch (err) {
    console.error("movies query error", err);
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Local filesystem movie sampler (uses MOVIE_DATA_ROOT). For demo only.
async function listLocalMovies(limit = 1) {
  const entries = await fs.readdir(MOVIE_DATA_ROOT, { withFileTypes: true });
  const folders = entries.filter((e) => e.isDirectory());
  const movies = [];
  for (const dirent of folders) {
    if (movies.length >= limit) break;
    const folderPath = path.join(MOVIE_DATA_ROOT, dirent.name);
    const metaFiles = (await fs.readdir(folderPath)).filter((f) =>
      f.endsWith("_metadata.txt")
    );
    const metaFile = metaFiles[0];
    if (!metaFile) continue;
    const metaRaw = await fs.readFile(path.join(folderPath, metaFile), "utf8");
    const metadata = {};
    metaRaw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .forEach((line) => {
        const [k, ...rest] = line.split(":");
        if (!k || rest.length === 0) return;
        metadata[k.trim()] = rest.join(":").trim();
      });
    const posterPath = path.join(folderPath, "poster.jpg");
    const posterExists = await fs
      .access(posterPath)
      .then(() => true)
      .catch(() => false);
    const screenshots = (await fs.readdir(folderPath))
      .filter((f) => f.toLowerCase().startsWith("screenshot"))
      .filter((f) => f.toLowerCase().endsWith(".jpg"));
    movies.push({
      folder: dirent.name,
      tmdb_id: metadata.id || "",
      title: metadata.title || dirent.name,
      release_date: metadata.release_date || "",
      tagline: metadata.tagline || "",
      poster: posterExists
        ? `/media/${encodeURIComponent(dirent.name)}/poster.jpg`
        : null,
      screenshots: screenshots.map(
        (file) => `/media/${encodeURIComponent(dirent.name)}/${file}`
      ),
      raw: metadata,
    });
  }
  return movies;
}

app.get("/api/local-movies", async (req, res) => {
  const limit = Number(req.query.limit || 1);
  try {
    const movies = await listLocalMovies(limit);
    res.json({ ok: true, count: movies.length, movies });
  } catch (err) {
    console.error("local-movies error", err);
    res
      .status(500)
      .json({ ok: false, error: err.message, root: MOVIE_DATA_ROOT });
  }
});

app.get("/api/tmdb/ping", async (req, res) => {
  const tmdbId =
    req.query.tmdb_id || process.env.TMDB_TEST_ID || "550"; // default Fight Club
  const apiKey = process.env.TMDB_API_KEY;
  if (!apiKey) {
    return res
      .status(400)
      .json({ ok: false, error: "TMDB_API_KEY not configured" });
  }
  try {
    const resp = await fetch(
      `https://api.themoviedb.org/3/movie/${tmdbId}?api_key=${apiKey}&append_to_response=images`
    );
    if (!resp.ok) {
      return res
        .status(resp.status)
        .json({ ok: false, error: `TMDB ${resp.status}` });
    }
    const data = await resp.json();
    res.json({
      ok: true,
      tmdb_id: tmdbId,
      title: data.title,
      posters: (data.images?.posters || []).length,
      backdrops: (data.images?.backdrops || []).length,
    });
  } catch (err) {
    console.error("tmdb ping error", err);
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Serve static test page(s) from /public
app.use(express.static("public"));

app.listen(PORT, () => {
  console.log(`API listening on http://localhost:${PORT}`);
  console.log(`MOVIE_DATA_ROOT: ${MOVIE_DATA_ROOT}`);
});
