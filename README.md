# ITIM — Intelligent Tutoring System for Mathematics

ITIM is an AI-powered Intelligent Tutoring System (ITS) designed for university, high school and middle school students. It combines a digital handwriting notebook with a conversational AI tutor that understands mathematics, monitors student behavior, and provides step-by-step guidance.

---

## Features

- **Handwriting & Infinite Canvas**  
  Write math freely with pen, eraser, and highlighter. The canvas captures strokes and performs spatial erasing.

- **Auto-OCR & LaTeX Conversion**  
  After a few seconds of inactivity, the system automatically captures the canvas and converts handwriting to LaTeX via a vision-language model.

- **Symbolic Math Verification**  
  Step-by-step solutions are checked using SymPy. The tutor knows when a step is correct, incorrect, or incomplete.

- **Buggy Rule Detection & Learning**  
  The system detects common misconceptions (e.g., binomial expansion errors) and **learns new buggy rules incrementally** from repeated student mistakes.

- **Conversational AI Tutor**  
  Natural-language chat with context-aware responses. Supports text, speech input (Whisper STT), and speech output (Orpheus TTS) with a hands-free conversation mode.

- **Document Import**  
  Import PDFs or images, extract mathematical concepts, and auto-generate relevant exercises. Documents can also be embedded as a canvas background.

- **Exercise Library & Generation**  
  Persistent SQLite-backed library with LLM-powered exercise generation, SymPy validation, and progressive difficulty scaling.

- **Cognitive Monitoring**  
  ACT-R inspired student modeling with knowledge tracing, cognitive load estimation (idle time, eraser frequency), and proactive pedagogical interventions.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3, FastAPI, Uvicorn |
| **Frontend** | React 19, Vite, Zustand |
| **Math Engine** | SymPy, pix2tex, latex2sympy2 |
| **LLM / Vision / Speech** | Groq API (GPT-OSS, Llama 4, Whisper, Orpheus) |
| **Database** | SQLite (custom store abstraction) |
| **Real-time** | WebSocket (`/ws`) |
| **PDF** | PDF.js (client), Pillow (server) |
| **Testing** | pytest (backend), vitest (frontend) |

---

## Project Structure

```
ITIM_v2/
├── .env.example              # Environment template
├── profiles/                 # Student profiles (SQLite + JSON)
├── src/
│   ├── Makefile              # Install, certs, dev, test
│   ├── backend/
│   │   ├── app/              # FastAPI app, WebSocket handlers, REST routes, sessions
│   │   ├── core/             # LLM client, persistence, profile manager
│   │   ├── domain/
│   │   │   ├── math/         # MathExpert, step tracker, AST utils, OCR pipeline
│   │   │   ├── cognitive/    # ACT-R façade, student model, dialogue manager, pedagogical agent
│   │   │   └── exercises/    # Exercise generator, library, document processor, buggy-rule learner
│   │   ├── input/            # Stroke buffer & stroke analyzer
│   │   ├── tutor/            # Main tutor orchestrator
│   │   └── test_backend.py
│   └── frontend/
│       ├── package.json
│       ├── vite.config.js
│       └── src/
│           ├── App.jsx
│           ├── ChatPanel.jsx
│           ├── components/canvas/   # Drawing canvas
│           ├── stores/              # Zustand state
│           ├── hooks/               # Canvas history, shortcuts
│           └── pdfService.js
```

---

## Prerequisites

- Python 3.10+
- Node.js + npm
- `mkcert` (for local HTTPS certificates)

---

## Installation

```bash
cd src
make install    # Installs Python dependencies + npm packages
make certs      # Generates localhost.pem / localhost-key.pem via mkcert
```

---

## Configuration

Create a `.env` file in the project root (or `src/backend/.env`):

```bash
GROQ_API_KEY=gsk_...   # Required for LLM, vision OCR, STT, and TTS
```

See `.env.example` for additional optional variables.

---

## Running the Application

### Development (both backend and frontend)

```bash
cd src
make dev
```

- Backend: `https://<local-ip>:9000`
- Frontend: `https://localhost:5173`

### Individual services

```bash
make backend     # Backend only
make frontend    # Frontend only
```

### Testing

```bash
make test        # Backend pytest suite
```

### Stop all services

```bash
make stop        # Kills processes on ports 9000 and 5173
```

---

## Deployment Note

The FastAPI backend can serve the built frontend statically from `frontend/dist/`. Build the frontend with:

```bash
cd src/frontend
npm run build
```

Then start the backend — it will automatically serve `index.html` for SPA routes.

---

## License

This project is developed for academic research purposes.
Authors : Amr Zaki Salih | Yagiz Efe Acar
