# VisionPV

AI-powered API for extracting structured data from scanned Tunisian accident reports (Procès-Verbal / PV). Uses Mistral OCR for vision processing and Mistral Large for text extraction, mapping Arabic/French documents into standardized JSON.

## Features

- **OCR**: Mistral OCR on PDF pages (200 DPI)
- **Stamp detection**: Dedicated crops for top-right and bottom-right F.T.U.S.A./ARRIVEE stamp (date du dépôt)
- **Structured extraction**: Victims, vehicles, causes, insurance, dates, delegation, etc.
- **Pydantic validation**: Request/response validation

## Setup

1. **Clone the repository**

2. **Create a `.env` file** at the root:
   ```env
   MISTRAL_API_KEY=your_mistral_api_key_here
   ```

3. **Install dependencies** (requires `poppler` for pdf2image):
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Run locally

```bash
python main.py
```

Server runs at `http://localhost:8000`.

### Run with Docker

```bash
docker compose build && docker compose up
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/vision-pv` | Upload PDF → structured JSON |
| GET | `/api/v1/` | Health check |
| GET | `/api/v1/health` | Health check |

### Example request

```bash
curl -X POST "http://localhost:8000/api/v1/vision-pv" \
  -F "file=@your_pv.pdf"
```

- **Input**: PDF file (multipart/form-data), max 50 MB
- **Output**: JSON with `N° du PV`, `Date du dépôt du PV`, `Date d'Accident`, victims, vehicles, causes, insurance, etc. (`Référence FTUSA` is excluded from the response)

## Pipeline

1. **PDF → images** (200 DPI)
2. **OCR** (Mistral OCR):
   - Pages 1–2: 4 crops each (top 70%, bottom 30%, stamp top-right, stamp bottom-right)
   - Pages 3+: full page
3. **Extraction** (Mistral Large): OCR text + stamp date → structured JSON
4. **Post-processing**: Age calculation from birth dates, reasoning fields removed

## Project structure

```
├── main.py          # FastAPI app, /api/v1/ routes
├── OCR_mistral.py   # PDF → OCR text + date_depot
├── LLM_mistral.py   # Text → structured JSON
├── prompt.py        # Extraction prompt template
├── schemas.py       # Pydantic request/response models
├── utils.py         # Logging utilities
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```
