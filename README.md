# Monolith Application

This project is a monolithic architecture setup inspired by the multi-service reference repository. 
It unifies backend services into a single Python backend and maintains a separate frontend.

## Architecture

- **Root/**
  - `backend/`: Python backend with FastAPI and gRPC.
    - `src/services/`: All business logic modules (agent_controller, users, etc.).
    - `src/adapters/`: Interfaces for external systems.
    - `src/core/`: Common utilities and logging.
  - `frontend/`: Vanilla JS frontend with Vite.
  - `protobuf/`: Shared contracts.
  - `docker-compose.yml`: Local development setup.

## Running Locally

```bash
docker-compose up
```

Backend: http://localhost:8000
Frontend: http://localhost:4173
