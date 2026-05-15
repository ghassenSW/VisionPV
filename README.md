# VisionPV

VisionPV is a robust, AI-powered API designed to automatically extract and structure data from Tunisian accident reports (Procès-Verbal). It leverages a multi-modal pipeline combining Mistral's advanced OCR capabilities with Google Gemini's Vision and Language models.

## Key Features
- **Multi-modal Pipeline:** Concurrent execution of Mistral OCR for full text extraction and Gemini Vision for targeted region extraction (e.g., arrival stamps).
- **Intelligent Fuzzy Matching:** Replaced heavy semantic embeddings with lightweight, hierarchical fuzzy logic to accurately map extracted entities (Cities, Vehicle Models, Insurances) to official FTUSA standard lists.
- **Modular Architecture:** Clean, production-ready FastAPI structure with strict separation of concerns (`app/services`, `app/core`, `data/`).
- **Resilience:** Built-in VLM retry mechanisms, strict JSON schema validation, and graceful error handling.
- **Docker Ready:** Fully containerized with a lightweight footprint, bypassing the need for heavy libraries like Pandas.
- **Secure:** Enforces explicit `.gitignore` rules shielding sensitive credentials (like `application_default_credentials.json`).

## Getting Started (Demo Guide)

### 1. Prerequisites
- Python 3.11+
- [Poppler](https://poppler.freedesktop.org/) (Required for PDF to Image conversion)
- API Keys for **Mistral AI** and **Google Gemini** (Vertex AI)

### 2. Environment Setup
Create a `.env` file in the root directory:
```env
MISTRAL_API_KEY=your_mistral_key_here
GOOGLE_APPLICATION_CREDENTIALS=gemini/application_default_credentials.json
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
GOOGLE_CLOUD_LOCATION=your_gcp_location
```
*Ensure your Google credentials JSON is securely placed at `gemini/application_default_credentials.json`.*

### 3. Local Installation
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 4. Running with Docker (Recommended)
```bash
docker-compose up --build -d
```
The API will be automatically available at `http://localhost:8080`.

## API Usage & Demo

The application comes with built-in interactive documentation via Swagger UI. Once the server is running, visit:
**[http://localhost:8080/docs](http://localhost:8080/docs)**

**Endpoint:** `POST /api/report/extract`

You can test this endpoint directly from the Swagger UI, or using cURL:

```bash
curl -X POST "http://localhost:8080/api/report/extract" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "requestId=demo-12345" \
  -F "reportFile=@/path/to/votre_rapport.pdf"
```

**Other Useful Endpoints:**
- `GET /api/version` - Check API version.
- `GET /api/health` - Check system health and available endpoints.

## Reference Data Update API

The API exposes several POST endpoints under the `/data` prefix to update reference lists used at runtime by the extraction pipeline. Each update endpoint accepts JSON payloads and will refresh the in-memory reference lists used by the LLM pipeline after a successful update.

Common request shapes (Pydantic schemas in `app/schemas.py`):

- `SimpleListUpdate` — `{ "items": ["Value A", "Value B"] }`
- `HierarchicalListUpdate` — `{ "items": { "Governorate A": ["Region 1", "Region 2"], "Governorate B": [...] } }`

Endpoints (all POST):

- `/api/regions/update` — Replace regions per governorate (accepts `HierarchicalListUpdate`). For each governorate key supplied, the endpoint deletes existing regions for that governorate and inserts the provided list; missing governorates are created.
- `/api/insurance-company/update` — Replace insurance companies (accepts `SimpleListUpdate`).
- `/api/claim-reason/update` — Replace claim reasons (accepts `SimpleListUpdate`).
- `/api/death-medical-cause/update` — Replace death medical causes (accepts `SimpleListUpdate`).
- `/api/health-institution/update` — Replace health institutions (accepts `SimpleListUpdate`).
- `/api/nav-guard-hq/update` — Replace naval guard HQs (accepts `SimpleListUpdate`).
- `/api/police-hq/update` — Replace police HQs (accepts `SimpleListUpdate`).
- `/api/social-state/update` — Replace social states (accepts `SimpleListUpdate`).
- `/api/vehicle-type/update` — Replace vehicle types (accepts `SimpleListUpdate`).

Examples (using `curl`, adjust host/port if running in Docker):

Replace claim reasons with two values:

```bash
curl -X POST "http://localhost:8080/api/claim-reason/update" \
  -H "Content-Type: application/json" \
  -d '{"items": ["Collision", "Vol"]}'
```

Update regions for two governorates:

```bash
curl -X POST "http://localhost:8080/api/regions/update" \
  -H "Content-Type: application/json" \
  -d '{"items": {"Tunis": ["Bab Saadoun", "Carthage"], "Sfax": ["Sakiet Ezzit", "Gremda"]}}'
```

Notes and behaviour:

- Each endpoint calls the runtime refresh function so subsequent extraction requests will use the updated lists immediately.
- Payloads must be valid JSON and use the `items` key as shown above.
- The API does not perform destructive truncation of unrelated tables — updates are scoped per endpoint (for example `regions/update` deletes and replaces regions only for the governorates present in the payload).
- Use the interactive docs at `/docs` to try endpoints from the browser and to see request/response examples.

