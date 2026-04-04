# Class Scheduling Engine

Backend microservice for automatic academic timetable generation. Solves the **NP-Complete Timetable Problem** for multi-campus institutions using Mixed-Integer Linear Programming.

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Task queue | Celery + Redis |
| Solver | PuLP / CBC (exact), Tabu Search stub (extensible) |
| Database | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Config | pydantic-settings (env vars / Docker secrets) |
| Real-time | WebSockets (FastAPI native) |
| Containerisation | Docker + Docker Compose |

---

## Project Structure

```
src/
├── domain/
│   ├── entities/          # Teacher, Subject, Room, Timeslot, Schedule
│   ├── value_objects/     # PenaltyWeights
│   ├── ports/             # ISolver, IScheduleRepository, IEventPublisher
│   └── services/          # SchedulingService
├── application/
│   ├── schemas/           # Pydantic input/output schemas
│   └── use_cases/         # GenerateSchedule, GetSchedule
├── infrastructure/
│   ├── config/            # Settings (pydantic-settings)
│   ├── solvers/           # PuLPSolver, TabuSearchSolverStub, SolverFactory
│   ├── persistence/       # SQLAlchemy models + repository
│   ├── messaging/         # Celery app + tasks
│   └── websockets/        # ConnectionManager
└── api/
    ├── routers/           # schedules, config, ws
    ├── dependencies.py    # DI wiring
    └── main.py            # FastAPI app
alembic/                   # DB migrations
tests/
├── unit/
└── integration/
```

---

## Running Locally

```bash
cp .env.example .env       # fill in values

# Full stack (api + worker + postgres + redis + flower dashboard)
docker compose --profile dev up --build
```

| Service | URL |
|---------|-----|
| API + Swagger | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| Celery Flower | http://localhost:5555 |

---

## API Endpoints

### Schedules

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/schedules/generate` | Submit generation job → returns `job_id` immediately |
| `GET` | `/api/v1/schedules/{job_id}` | Poll status and result |
| `GET` | `/api/v1/schedules/` | List all jobs |
| `DELETE` | `/api/v1/schedules/{job_id}` | Delete a job |

### Configuration

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/config/penalties` | Get penalty weights |
| `PUT` | `/api/v1/config/penalties` | Update penalty weights |

### Real-time

| Protocol | Path | Description |
|----------|------|-------------|
| WebSocket | `/ws/{job_id}` | Push notifications on job completion |

---

## Generate Request (minimal example)

```bash
curl -X POST http://localhost:8000/api/v1/schedules/generate \
  -H "Content-Type: application/json" \
  -d '{
    "teachers": [
      {
        "id": "T1", "name": "Prof A",
        "teacher_type": "REGULAR",
        "campus_ids": ["C1"],
        "availability_slots": [],
        "max_hours_per_day": 6
      }
    ],
    "subjects": [
      {
        "id": "S1", "name": "Calculo",
        "group_id": "G1", "required_sessions": 2,
        "campus_id": "C1", "student_count": 30
      }
    ],
    "rooms": [
      { "id": "R1", "name": "Aula 101", "campus_id": "C1", "capacity": 40 }
    ],
    "timeslots": [
      { "id": "TS1", "day": 0, "slot_index": 0, "start_time": "07:00", "end_time": "09:00" },
      { "id": "TS2", "day": 1, "slot_index": 0, "start_time": "07:00", "end_time": "09:00" }
    ],
    "penalty_weights": { "penalizacion1": 2.0, "penalizacion2": 1.0 },
    "solver": "pulp_cbc",
    "time_limit_seconds": 300
  }'
```

Response:
```json
{ "job_id": "...", "ws_url": "ws://localhost:8000/ws/..." }
```

---

## Teacher Types

| Type | Description |
|------|-------------|
| `REGULAR` | Standard teacher — single campus |
| `PROCOM` | Shared across ≥ 2 campuses — inter-campus travel penalised (`penalizacion1`) |
| `PROJEX` | Extended-hours only — assigned to slots after 18:00 |
| `PROHES` | Special schedule — assigned exactly `½ × ntpphes` distinct days per campus |

---

## Constraints Implemented

### Hard (from Esquivel Tovar 2014 / MM.lng)

| ID | Description |
|----|-------------|
| R4 | Teacher teaches ≤ 1 class per (day, slot) |
| R5 | Teacher ≤ `max_hours_per_day` periods per day |
| R6 | Subject intensity: exactly `required_sessions` assignments |
| R7 | Room not double-booked per (day, slot) |
| R8 | Room capacity ≥ subject student count |
| R9 | Teacher availability windows respected |
| R10 | PROCOM teachers cannot teach campus A at slot `t` and campus B at slot `t+1` |
| R13 | PROHES teachers assigned exactly `½ × ntpphes` days per campus |

### Soft (Objective Function)

```
MIN = Σ BZ(subject, day) × penalizacion2   ← gap/bache penalty
    + Σ BY(teacher, campus, day, slot) × penalizacion1  ← PROCOM transfer penalty
```

---

## Database Migrations

```bash
# Apply all migrations
SYNC_DATABASE_URL=postgresql+psycopg2://scheduler:changeme@localhost:5432/scheduling_db \
  alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"
```

---

## Tests

```bash
PYTHONPATH=. pytest tests/unit/ -v         # unit tests (no DB/Redis required)
PYTHONPATH=. pytest tests/integration/ -v  # requires docker compose up
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Required at runtime:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Async PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `SYNC_DATABASE_URL` | Sync DSN for Alembic (`postgresql+psycopg2://...`) |
| `REDIS_URL` | Redis DSN |
| `CELERY_BROKER_URL` | Redis broker URL |
| `CELERY_RESULT_BACKEND` | Redis result backend URL |
| `SECRET_KEY` | ≥ 16-char random string |
| `SOLVER_TIME_LIMIT` | CBC time limit in seconds (default: 300) |
| `PENALTY1_DEFAULT` | Default `penalizacion1` (default: 2.0) |
| `PENALTY2_DEFAULT` | Default `penalizacion2` (default: 1.0) |
