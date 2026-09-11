from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def get_users():
    return []

@app.get("/code-only")
def code_only():
    return {"message": "implemented only"}

@app.post("/conflict-path")
def conflict_path():
    return {"message": "implemented as POST"}
