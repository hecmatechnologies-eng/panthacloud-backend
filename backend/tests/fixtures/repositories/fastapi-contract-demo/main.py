from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    return [{"id": "1", "name": "Alice"}]

@app.post("/users")
def create_user():
    return {"id": "2", "name": "Bob"}

@app.get("/users/{id}")
def get_user_by_id(id: str):
    return {"id": id, "name": "Alice"}
