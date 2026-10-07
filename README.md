# CarbonShift AI

CarbonShift AI is a spatial-temporal scheduling system that dynamically shifts computational workloads across India to minimize carbon emissions, powered by a Grid Digital Twin and a CP-SAT optimizer.

## Quickstart

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Setup Backend:
   ```bash
   make setup-backend
   ```

3. Start Backend:
   ```bash
   make start-backend
   ```

4. Reset Database & Load Demo Data:
   ```bash
   make db-reset
   ```

5. Setup & Start Frontend:
   ```bash
   make setup-frontend
   make start-frontend
   ```

## Architecture

- **Backend:** FastAPI, SQLModel (SQLite), OR-Tools CP-SAT
- **Frontend:** React, Vite, TailwindCSS
- **Data:** Grid Digital Twin (physics-based simulation of Indian power grid)
