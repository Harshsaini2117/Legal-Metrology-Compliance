from fastapi import FastAPI

app = FastAPI(
    title="SIH26034 Compliance API",
    description="Packaged Commodity Legal Metrology Compliance System",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "project": "SIH26034",
        "service": "compliance-api",
    }