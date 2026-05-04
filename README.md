# VisionPV 📄👁️

VisionPV is a robust, AI-powered API designed to automatically extract and structure data from Tunisian accident reports (Procès-Verbal). It leverages a multi-modal pipeline combining Mistral's advanced OCR capabilities with Google Gemini's Vision and Language models.

## ✨ Key Features
- **Multi-modal Pipeline:** Concurrent execution of Mistral OCR for full text extraction and Gemini Vision for targeted region extraction (e.g., arrival stamps).
- **Intelligent Fuzzy Matching:** Replaced heavy semantic embeddings with lightweight, hierarchical fuzzy logic to accurately map extracted entities (Cities, Vehicle Models, Insurances) to official FTUSA standard lists.
- **Modular Architecture:** Clean, production-ready FastAPI structure with strict separation of concerns (`app/services`, `app/core`, `data/`).
- **Resilience:** Built-in VLM retry mechanisms, strict JSON schema validation, and graceful error handling.
- **Docker Ready:** Fully containerized with a lightweight footprint, bypassing the need for heavy libraries like Pandas.
- **Secure:** Enforces explicit `.gitignore` rules shielding sensitive credentials (like `application_default_credentials.json`).

## 🚀 Getting Started (Demo Guide)

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

## 📡 API Usage & Demo

The application comes with built-in interactive documentation via Swagger UI. Once the server is running, visit:
👉 **[http://localhost:8080/docs](http://localhost:8080/docs)**

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
