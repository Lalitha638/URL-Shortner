# Snipr — URL Shortener with Click Analytics

A full-stack URL shortener built with **FastAPI + SQLite + vanilla HTML/CSS/JS**.
Paste a long URL, get a short one back, and track every click that happens on it —
including device type, referrer, and clicks-per-day, shown on a dashboard with a chart.

---

## 1. Project structure

```
url-shortener/
│
├── backend/
│   ├── main.py            # FastAPI app — all API routes live here
│   ├── database.py        # SQLite connection + table creation
│   ├── models.py          # Pydantic request/response models
│   ├── requirements.txt   # Python dependencies
│   └── shortener.db       # (created automatically on first run)
│
├── frontend/
│   ├── index.html         # Page to create a short link
│   ├── dashboard.html     # Analytics dashboard (table + chart)
│   ├── style.css          # Shared styling for both pages
│   └── script.js          # Talks to the backend API (fetch calls)
│
└── README.md
```

---

## 2. Setup in PyCharm

1. **Open the project**: `File → Open` → select the `url-shortener` folder.
2. **Create a virtual environment** (PyCharm usually prompts you automatically):
   - `File → Settings → Project → Python Interpreter → Add Interpreter → Add Local Interpreter → Virtualenv Environment`
   - Base it on `backend/` or the project root — either works.
3. **Install dependencies.** Open PyCharm's built-in Terminal (bottom toolbar) and run:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
4. **Mark `backend` as a Sources Root (optional but tidy)**: right-click the `backend`
   folder in the Project panel → `Mark Directory as → Sources Root`. This helps
   PyCharm resolve the imports between `main.py`, `database.py`, `utils.py`, `models.py`.

---

## 3. Running the project

### Start the backend

In PyCharm's Terminal:

```bash
cd backend
uvicorn main:app --reload
```

You should see:

```
Database ready at: .../backend/shortener.db
Uvicorn running on http://127.0.0.1:8000
```

Leave this terminal running. Visit **http://127.0.0.1:8000/docs** in your browser —
that's FastAPI's auto-generated interactive API tester. Try `POST /api/shorten`
there directly if you want to test the backend before touching the frontend.

### Open the frontend

The frontend is plain HTML/CSS/JS, so it doesn't need its own server — but browsers
are picky about `fetch()` calls from `file://` pages, so the easiest reliable way is:

- **In PyCharm**: right-click `frontend/index.html` → `Open in Browser` (PyCharm runs
  a tiny local server for you automatically), **or**
- Install the free **"Live Server"**-style plugin, **or**
- Just double-click `index.html` to open it directly — it works too, since the
  backend already allows all origins (`CORS: allow_origins=["*"]`).

Once open:
1. Go to **index.html** → paste a long URL → click **Shorten link**.
2. Copy the short link it gives you, or scan the QR code.
3. Open the short link in a new tab a few times (it'll redirect you to the original URL).
4. Go to **dashboard.html** → see your link, its click count, and the clicks-per-day chart.

---

## 4. API endpoints

| Method | Endpoint                     | Purpose                                      |
|--------|-------------------------------|-----------------------------------------------|
| GET    | `/`                            | Health check                                  |
| POST   | `/api/shorten`                 | Create a short link                           |
| GET    | `/{short_code}`                 | Redirect to the original URL, logs the click |
| GET    | `/api/links?search=`           | List all links (optional search)              |
| GET    | `/api/stats/{short_code}`      | Detailed analytics for one link               |
| GET    | `/api/analytics/overview`      | Totals + 7-day chart data + top links         |
| DELETE | `/api/links/{short_code}`      | Delete a link and its click history           |
| GET    | `/api/qr/{short_code}`         | PNG QR code for the short link                |

---

## 5. How it works (beginner explanation)

**Creating a short link:**
1. You paste a long URL into `index.html`. JavaScript (`script.js`) sends it with
   `fetch()` to `POST /api/shorten`.
2. FastAPI validates the URL, saves a new row in the `links` table, and gets back
   the row's auto-generated `id` from SQLite (e.g. `125`).
3. That `id` is converted into a short, URL-safe code using **base62 encoding**
   (digits 0–9 + lowercase + uppercase letters = 62 symbols). `125` might become
   `"cD"` — much shorter than typing out the number, and it doesn't reveal how
   many links exist in the system.
4. If you typed a **custom alias** instead (like `my-sale`), we just use that
   directly — after checking it isn't already taken.
5. The short code is saved back into that row, and the frontend shows you the
   final short link plus a QR code.

**Clicking a short link:**
1. Someone opens `http://127.0.0.1:8000/abc123`.
2. FastAPI's `GET /{short_code}` route looks up `abc123` in the `links` table.
3. If found (and not expired), it does two things:
   - Inserts a new row into the `clicks` table (timestamp, referrer, device type).
   - Sends the browser a `302` redirect to the original long URL.
4. We deliberately use **302 (temporary)** instead of **301 (permanent)** —
   browsers cache 301 redirects and stop asking our server on repeat visits,
   which would mean we stop being able to count clicks.

**The dashboard:**
- `dashboard.html` calls `GET /api/analytics/overview` (totals + chart data) and
  `GET /api/links` (the table of all links) when the page loads.
- The bar chart is drawn with **Chart.js**, using clicks grouped by day from the
  `clicks` table.
- Clicking **Delete** calls `DELETE /api/links/{code}`, which removes the link
  and all its click history.

**Rate limiting (why it's there):**
The `/api/shorten` endpoint tracks how many requests each IP address has made
in the last 60 seconds, in a simple in-memory dictionary. If someone goes over
20 requests/minute, they get a `429 Too Many Requests` error. This stops one
person from spamming the database with junk links. (A real production system
would use Redis for this instead of an in-memory dictionary, since memory
resets every time the server restarts — but the concept is the same.)

---

## 6. Talking points for interviews

If you're asked "walk me through your project," here's the shape of a strong answer:

1. **What it does** — "It's a URL shortener with click analytics, similar to Bitly."
2. **The interesting problem** — "Generating short codes without them colliding.
   I used base62 encoding on the database's own auto-increment ID, which
   guarantees uniqueness by construction, rather than generating a random
   string and hoping it isn't taken."
3. **A trade-off you made** — "I used a 302 redirect instead of 301 on purpose,
   because 301s get cached by the browser and I'd lose the ability to count
   repeat clicks."
4. **How you'd extend it** — "I'd add user accounts so links belong to specific
   people, move the rate limiter to Redis so it survives a restart, and add
   geographic click data using an IP-lookup service."

---

## 7. Git workflow

```bash
git init
git add .
git commit -m "Initial commit: URL shortener with analytics"
git branch -M main
git remote add origin https://github.com/your-username/your-repo-name.git
git push -u origin main
```

For every change after that, just:

```bash
git add .
git commit -m "your message here"
git push
```

**Tip:** create a `.gitignore` (already included) so your database file and
Python cache folders don't get committed.



Image 1 :<img width="1806" height="1077" alt="image" src="https://github.com/user-attachments/assets/d3d3e4e4-6b89-40cb-9db1-b3c314e4a037" />
Image 2:<img width="1798" height="1080" alt="image" src="https://github.com/user-attachments/assets/5a539eb2-1fd8-4427-84ff-fe54950f8e3c" />


