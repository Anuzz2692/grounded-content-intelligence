# Setup guide: run Grounded Content Studio on your own computer

This guide takes you from nothing installed to a working app. Pick the path that suits you:

| Path | You need | Time | What you get |
|---|---|---|---|
| **A. Offline demo** | Python and Node | about 10 minutes | The full interface with a pretend website and pretend model. No keys, no downloads of AI models. |
| **B. Local AI (Ollama)** | A + Ollama and a model | about 30 minutes | Real writing on your own machine. Private and free after the model download. |
| **C. Claude (cloud)** | A + an Anthropic API key | about 15 minutes | Real writing with Anthropic Claude (usage is billed to your account). |
| **D. Both** | B + C | about 40 minutes | Claude first, and your local model as the automatic fallback. |

Start with **A** to see the app working, then add B and/or C.

---

## 1. What you need

### Required software

| Requirement | Version | Why | Check it |
|---|---|---|---|
| **Python** | 3.10 or newer (tested on 3.13) | The backend | `python --version` (Windows: `py --version`) |
| **pip** | comes with Python | Installs the libraries below | `pip --version` |
| **Node.js and npm** | Node 18 or newer (tested on 22) | Builds the web interface | `node --version` and `npm --version` |
| **Git** | any recent version | Downloads the project | `git --version` |

Downloads: [python.org](https://www.python.org/downloads/) (on Windows, tick "Add python.exe to PATH" in the installer), [nodejs.org](https://nodejs.org/) (the LTS version), [git-scm.com](https://git-scm.com/downloads).

### Python libraries (installed automatically from `requirements.txt`)

| Library | Used for |
|---|---|
| `fastapi` | The web API |
| `uvicorn[standard]` | The server that runs the API |
| `anthropic` | Talking to Claude (needed even if you only use Ollama, because the code imports it) |
| `httpx` | Reading websites and calling Ollama |
| `beautifulsoup4` | Extracting text from web pages |
| `pydantic-settings` | Reading the `.env` settings file |
| `cachetools` | Caching research results |

For running the tests, `requirements-dev.txt` adds `pytest`, `pytest-asyncio` and `respx`.

### Web interface libraries (installed by `npm install`)

`react` and `react-dom` run in the browser. `vite`, `@vitejs/plugin-react`, `vitest` and `jsdom` are only for building and testing.

### An AI model (needed for paths B, C and D, not for the demo)

You need **at least one** of these:

- **Ollama with a model** (local, free, private). See section 5.
- **An Anthropic API key** (cloud, paid per use). See section 6.

### Hardware for local models (path B)

These are rough guides, not guarantees:

- **RAM:** a 7B model such as `qwen2.5:7b` or `mistral:7b` needs roughly 5 to 6 GB free for the model itself. 8 GB of total RAM is tight, 16 GB is comfortable.
- **Disk:** about 4 to 5 GB per 7B model download.
- **CPU or GPU:** a GPU makes it much faster, but a CPU works. On an ordinary laptop CPU expect one to three minutes for a long page, less for short formats.
- **Internet:** needed to download the model once, and to read the website you point the studio at. Generation itself then runs locally.

### Ports used

| Port | What |
|---|---|
| `8000` | The studio (interface and API) |
| `11434` | Ollama, if you use it |
| `5173` | Only when running the interface in development mode |

---

## 2. Download the project

```bash
git clone https://github.com/your-username/grounded-content-studio.git
cd grounded-content-studio
```

(Replace the address with the real repository address, or download and unzip the project and open a terminal in that folder.)

---

## 3. Install the backend

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell refuses to run the activation script ("running scripts is disabled"), run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

You should now see `(.venv)` at the start of your prompt. **Every time you open a new terminal, activate the environment again** (the `Activate.ps1` or `source` line) before running the app.

---

## 4. Build the web interface

```bash
cd frontend
npm install
npm run build
cd ..
```

This creates `frontend/dist`, which the backend serves at `http://127.0.0.1:8000`. Run `npm run build` again whenever the files in `frontend/src` change.

If you skip this step the app still runs, but only as an API (there is no web page).

---

## Path A: try the offline demo

```bash
python -m demo.run
```

Open **http://127.0.0.1:8000**. Type a topic and press **Generate content**. Stop the demo with `Ctrl+C`.

The demo starts a pretend website ("Example Co") and a pretend AI model that returns canned text, then runs the real application against them. It shows the whole workflow, including the review tab, wording fixes and the calendar brief, but **the writing is not real**. It is meant for looking around, not for real content.

---

## 5. Path B: use local AI with Ollama

### 5.1 Install Ollama

Download it from [ollama.com/download](https://ollama.com/download) and install it. On Windows and macOS the Ollama app starts a background service automatically. On Linux the installer sets up a service, or you can run `ollama serve` in a separate terminal.

### 5.2 Download a model

```bash
ollama pull qwen2.5:7b
ollama list
```

`ollama list` should show the model. Other 7B models also work, for example `mistral:7b`. A bigger model writes better but needs more memory and time.

Check that Ollama is answering:

```bash
curl http://localhost:11434/api/tags
```

(PowerShell: `Invoke-RestMethod http://localhost:11434/api/tags`.) You should see your model in the list.

### 5.3 Tell the studio to use it

Open `.env` in a text editor and set:

```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

`OLLAMA_MODEL` must match the name from `ollama list` **exactly**. If you pulled `mistral:7b`, write `mistral:7b`.

### 5.4 Choose the website

By default the studio reads `https://example.com/`, which has almost no content. Point it at the site you want content for, either by setting this in `.env`:

```
WEBSITE_BASE_URL=https://www.your-company.example/
```

or by editing `website_url` in `companies/example_company/profile.json`. For several companies see section 10.

### 5.5 Start the studio

```bash
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. In the top right you should see **Server online · Ollama**. If it says **Ollama not running** or **Ollama model missing**, go back to 5.1 or 5.2.

The first request after starting can be slow while Ollama loads the model into memory.

---

## 6. Path C: use Claude (Anthropic)

1. Create an account at [console.anthropic.com](https://console.anthropic.com/) and create an API key. Usage is billed by Anthropic.
2. Put the key in `.env`:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
ANTHROPIC_MODEL=claude-sonnet-4-5
```

Set `ANTHROPIC_MODEL` to a model your account can use (model names change over time; see Anthropic's documentation).

3. Start the studio (`uvicorn app.main:app --reload`) and open http://127.0.0.1:8000.

**Keep your key private.** `.env` is listed in `.gitignore`, so Git will not upload it. Never paste a real key into a file that is committed, a screenshot or a chat.

### Path D: Claude with a local fallback

```
LLM_PROVIDER=auto
ANTHROPIC_API_KEY=your-key-here
OLLAMA_MODEL=qwen2.5:7b
```

In `auto` mode the studio tries Claude first and uses Ollama if Claude fails (no key, rate limit, timeout). The **Details** tab shows which one wrote the content and why a fallback happened.

### Provider modes at a glance

| `LLM_PROVIDER` | Behaviour |
|---|---|
| `ollama` | Only your local model. No key needed. |
| `anthropic` | Only Claude. Needs `ANTHROPIC_API_KEY`. |
| `auto` | Claude first, Ollama as the fallback. |

---

## 7. Using the studio

### In the browser

1. **Type what you want written** (or click an example topic).
2. Choose a **format** (website page, blog post, FAQ, social post, video script, general) and a **length**.
3. Leave **Writing polish** on *Natural* for a guarded rewrite, or choose *Light* or *Off* for faster, plainer results.
4. Leave **Run the brand check and claim scan** on if you want a review briefing. Turn it off for a fast, unreviewed draft.
5. Press **Generate content** (or `Ctrl+Enter`).

Then look through the result:

- **Content**: the draft. You can edit it, copy it, or download it as Markdown or text. "Copy text only" leaves out tags and labels.
- **Review**: the brand check, a list of sentences the claim scan flagged (each has its own **Apply this change** button), the writer's notes and a briefing for a human reviewer.
- **Sources**: the website pages the AI was given, with links.
- **Details**: how long each step took and which model wrote it.

Nothing is ever approved or published by the studio. A person has to review the result.

### Calendar brief for a presenter-led video

Choose **Video script**, switch on **Use a calendar brief**, and fill in at least the duration, approved hook, approved call to action and approved claims (one per line as `ID: statement`). The generate button stays disabled until those are filled in, because the studio will not invent them. The result tab **Script** shows the title, hook, a four-column script table, caption, hashtags, the claims used and a 20-point self-check.

### From the command line (API)

macOS or Linux:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/content/generate \
  -H "Content-Type: application/json" \
  -d '{"query": "Explain how a home battery backup works", "content_type": "article", "length": "standard"}'
```

Windows PowerShell:

```powershell
$body = @{ query = "Explain how a home battery backup works"; content_type = "article"; length = "standard" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/content/generate" -Method Post -ContentType "application/json" -Body $body
```

Interactive API documentation is at http://127.0.0.1:8000/docs.

---

## 8. Settings you may want to change

All settings live in `.env` (restart the server after changing them).

| Setting | Default | When to change it |
|---|---|---|
| `LLM_PROVIDER` | `auto` | Set to `ollama` if you have no Claude key |
| `OLLAMA_MODEL` | `qwen2.5:7b` | When you use a different local model |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | Raise it on a slow computer |
| `OLLAMA_NUM_CTX` / `OLLAMA_MAX_CTX` | `8192` / `16384` | Lower them if you run out of memory |
| `WEBSITE_BASE_URL` | empty (uses the profile) | To point at another website |
| `API_KEYS` | empty | Set it (comma-separated) if others can reach the server |
| `RATE_LIMIT_PER_MINUTE` | `10` | `0` switches the limit off |
| `FORMAT_REPAIR` | `true` | `false` saves one model call per request |
| `HUMANIZE_ENABLED` | `true` | `false` turns the polish pass off everywhere |
| `COMPANY` | `example_company` | To switch company (section 10) |

`.env.example` explains every option.

---

## 9. Letting other devices on your network use it

By default the studio listens only on your own computer. To open it from a phone or another PC on the same network:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

then open `http://<this-computer's-ip-address>:8000` on the other device. **Before you do this, set `API_KEYS` in `.env`**, because without it anyone who can reach the port can use your model (and your Claude credit). In the web page, add the key under Settings (the gear icon). Do not expose the studio to the public internet without a proper reverse proxy, HTTPS and keys.

---

## 10. Using it for another company

```bash
python -m app.company new acme --name "Acme Corp" --url https://www.acme.example/
python -m app.company check acme
```

This creates `companies/acme/` with a `profile.json` and a copy of every prompt. Edit the prompts and profile, add the company's real guidelines as `companies/acme/prompts/brand_guidelines.md`, set `COMPANY=acme` in `.env`, and restart. The README explains the profile fields.

---

## 11. Developing and testing

Run the interface with hot reload (in a second terminal, while the backend is running):

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. It forwards `/api` and `/health` to the backend on port 8000.

Run the tests (they use mocked models, so no keys, network or Ollama are needed):

```bash
pip install -r requirements-dev.txt
pytest

cd frontend
npm test
```

---

## 12. Troubleshooting

| What you see | Likely cause and fix |
|---|---|
| `python` or `py` is not recognised | Python is not installed or not on PATH. Reinstall and tick "Add to PATH" (Windows), or use `python3` (macOS/Linux). |
| `ModuleNotFoundError: No module named 'app'` | You are not in the project folder. `cd` into `grounded-content-studio` and run the command again. |
| `ModuleNotFoundError` for `fastapi`, `anthropic` and so on | The virtual environment is not active, or the install did not finish. Activate `.venv` and run `pip install -r requirements.txt`. |
| PowerShell: "running scripts is disabled" | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again. |
| Browser shows `{"detail":"Not Found"}` at `/` | The interface is not built. Run `npm install` and `npm run build` in `frontend`, then restart. |
| `npm` is not recognised | Install Node.js (LTS) and open a new terminal. |
| Header says **Ollama not running** | Ollama is not running. Start the Ollama app, or run `ollama serve`. |
| Header says **Ollama model missing**, or a `404` from Ollama | Run `ollama pull <model>` and make sure `OLLAMA_MODEL` in `.env` matches `ollama list` exactly. |
| "No LLM provider could generate content" | With `LLM_PROVIDER=auto` and no working key, Ollama must be running with the model installed. The message lists why each provider failed (`auth`, `timeout`, `connection`, `model_not_found`). |
| `auth` reason | The Anthropic key is missing or wrong. Check `ANTHROPIC_API_KEY`, or switch to `LLM_PROVIDER=ollama`. |
| `timeout` reason, or very slow | A local model on CPU is slow. Raise `OLLAMA_TIMEOUT_SECONDS`, choose a "concise" length, use a smaller model, or turn off the polish pass. |
| `429` "too many requests" | The rate limit. Wait, or set `RATE_LIMIT_PER_MINUTE=0` for local use. |
| `401` "needs a valid API key" | `API_KEYS` is set in `.env`. Add one of those keys under Settings in the page, or send it in an `X-API-Key` header. |
| Port 8000 already in use | Another program uses it. Stop it, or start with `--port 8001`. |
| "The website could not be read" (502) | The site is unreachable, blocks automated requests, or builds its pages with JavaScript so there is little text to read. Try another site or check `WEBSITE_BASE_URL`. |
| Content is thin or off-topic | The studio only writes from what it can read on the site. Ask about something the site actually covers. |
| Review tab always says "Blocked" or "Needs review" | No brand guidelines are set for your company, so the brand check cannot pass. Add `companies/<your-company>/prompts/brand_guidelines.md` (see section 10). This is intentional; the bundled sample company ships a sample guideline so the demo can pass. |
| Brief form: Generate button disabled | A required brief field is empty or a line is not in `ID: statement` form. The problems are listed under the form. |

If you change `.env`, **restart the server**. If you change anything in `frontend/src`, **rebuild** with `npm run build`.

---

## 13. Updating and removing

Update:

```bash
git pull
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

Remove: delete the project folder. Your browser also keeps recent drafts and form settings in its local storage; clear the site data for `127.0.0.1:8000` to remove them. Ollama models stay installed until you run `ollama rm <model>`.

---

## 14. Good to know

- The studio can make mistakes. It cannot prove a statement is true, and a person must review everything before it is used.
- Only point it at websites you are allowed to read automatically, and follow their terms of use.
- Local 7B models follow the strict formats well, but their writing is less careful than Claude's. Review their output closely.
- Your drafts are stored only in your browser. The server keeps no content, only a short-lived cache of the pages it read.
